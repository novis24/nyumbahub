from dataclasses import dataclass
from math import floor

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.listings.models import (
    GlobalVideoStoragePolicy,
    ListingVideoStatus,
    VideoReservationStatus,
    VideoUploadReservation,
)


USER_MESSAGE_UNAVAILABLE = 'Video uploads are temporarily unavailable. Your existing videos remain available.'


@dataclass(frozen=True)
class CapacitySnapshot:
    cap_bytes: int
    committed_bytes: int
    reserved_bytes: int
    available_bytes: int
    standard_video_bytes: int
    estimated_remaining_videos: int
    uploads_enabled: bool
    recording_enabled: bool
    optimization_enabled: bool

    def as_dict(self):
        return self.__dict__.copy()


def snapshot_policy():
    policy = GlobalVideoStoragePolicy.get_solo()
    return _snapshot(policy)


def reserve_video_capacity(*, user, listing, video, declared_size, optimize=False):
    expected_processed = min(declared_size, _policy_hard_size())
    temporary_bytes = declared_size + (expected_processed if optimize else 0)
    final_bytes = expected_processed if optimize else declared_size
    peak_required = temporary_bytes + final_bytes

    with transaction.atomic():
        GlobalVideoStoragePolicy.get_solo()
        policy = GlobalVideoStoragePolicy.objects.select_for_update().get(pk=1)
        if not policy.uploads_enabled or policy.global_storage_cap_bytes <= 0:
            return None, USER_MESSAGE_UNAVAILABLE
        if policy.committed_bytes + policy.reserved_bytes + peak_required > policy.global_storage_cap_bytes:
            return None, USER_MESSAGE_UNAVAILABLE

        policy.reserved_bytes += peak_required
        policy.save(update_fields=['reserved_bytes', 'updated_at'])
        reservation = VideoUploadReservation.objects.create(
            user=user,
            tenant=getattr(user, 'role', '') or '',
            listing=listing,
            video=video,
            object_key=video.object_key,
            declared_size=declared_size,
            expected_processed_size=expected_processed,
            reserved_temporary_bytes=temporary_bytes,
            reserved_final_bytes=final_bytes,
            expiration_time=video.upload_expires_at,
            status=VideoReservationStatus.UPLOADING,
        )
        return reservation, ''


def mark_uploaded_temporarily(reservation, actual_size):
    with transaction.atomic():
        reservation = VideoUploadReservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.status in {VideoReservationStatus.COMPLETED, VideoReservationStatus.UPLOADED_TEMPORARILY}:
            return reservation
        reservation.actual_uploaded_size = actual_size
        reservation.status = VideoReservationStatus.UPLOADED_TEMPORARILY
        reservation.save(update_fields=['actual_uploaded_size', 'status'])
        return reservation


def complete_reservation(reservation, actual_final_size):
    with transaction.atomic():
        policy = GlobalVideoStoragePolicy.objects.select_for_update().get(pk=1)
        reservation = VideoUploadReservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.status == VideoReservationStatus.COMPLETED:
            return reservation

        released = reservation.active_reserved_bytes
        policy.reserved_bytes = max(policy.reserved_bytes - released, 0)
        policy.committed_bytes += actual_final_size
        policy.save(update_fields=['reserved_bytes', 'committed_bytes', 'updated_at'])

        reservation.actual_processed_size = actual_final_size
        reservation.status = VideoReservationStatus.COMPLETED
        reservation.completed_time = timezone.now()
        reservation.save(update_fields=['actual_processed_size', 'status', 'completed_time'])
        return reservation


def release_reservation(reservation, status=VideoReservationStatus.FAILED, reason=''):
    with transaction.atomic():
        policy = GlobalVideoStoragePolicy.objects.select_for_update().get(pk=1)
        reservation = VideoUploadReservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.status in {VideoReservationStatus.COMPLETED, VideoReservationStatus.FAILED, VideoReservationStatus.EXPIRED, VideoReservationStatus.REJECTED, VideoReservationStatus.DELETED}:
            return reservation
        released = reservation.active_reserved_bytes
        policy.reserved_bytes = max(policy.reserved_bytes - released, 0)
        policy.save(update_fields=['reserved_bytes', 'updated_at'])
        reservation.status = status
        reservation.failure_reason = reason[:255]
        reservation.completed_time = timezone.now()
        reservation.save(update_fields=['status', 'failure_reason', 'completed_time'])
        return reservation


def release_committed_video(video):
    with transaction.atomic():
        GlobalVideoStoragePolicy.get_solo()
        policy = GlobalVideoStoragePolicy.objects.select_for_update().get(pk=1)
        policy.committed_bytes = max(policy.committed_bytes - int(video.file_size or 0), 0)
        policy.save(update_fields=['committed_bytes', 'updated_at'])


def expire_stale_reservations():
    expired = 0
    for reservation in VideoUploadReservation.objects.filter(
        status__in=[
            VideoReservationStatus.RESERVED,
            VideoReservationStatus.UPLOADING,
            VideoReservationStatus.UPLOADED_TEMPORARILY,
            VideoReservationStatus.QUEUED,
            VideoReservationStatus.PROCESSING,
        ],
        expiration_time__lt=timezone.now(),
    ):
        release_reservation(reservation, VideoReservationStatus.EXPIRED, 'Upload reservation expired.')
        video = reservation.video
        if video and video.upload_status != ListingVideoStatus.READY:
            video.upload_status = ListingVideoStatus.FAILED
            video.error_message = 'Upload session expired.'
            video.save(update_fields=['upload_status', 'error_message', 'updated_at'])
        expired += 1
    return expired


def user_video_usage_bytes(user):
    return user.listing_videos.filter(upload_status=ListingVideoStatus.READY).aggregate(total=Sum('file_size'))['total'] or 0


def remaining_standard_videos(user, allowance_bytes, standard_video_bytes):
    if not allowance_bytes or not standard_video_bytes:
        return 0
    remaining = max(allowance_bytes - user_video_usage_bytes(user), 0)
    return floor(remaining / standard_video_bytes)


def _snapshot(policy):
    return CapacitySnapshot(
        cap_bytes=policy.global_storage_cap_bytes,
        committed_bytes=policy.committed_bytes,
        reserved_bytes=policy.reserved_bytes,
        available_bytes=policy.available_bytes,
        standard_video_bytes=policy.standard_video_bytes,
        estimated_remaining_videos=floor(policy.available_bytes / policy.standard_video_bytes) if policy.standard_video_bytes else 0,
        uploads_enabled=policy.uploads_enabled,
        recording_enabled=policy.recording_enabled,
        optimization_enabled=policy.optimization_enabled,
    )


def _policy_hard_size():
    return GlobalVideoStoragePolicy.get_solo().hard_video_size_bytes
