from dataclasses import dataclass
from pathlib import Path

from django.db.models import Sum

from apps.subscriptions.models import VideoPlanEntitlement
from apps.listings.models import ListingVideoStatus
from apps.listings.services.video_quota import remaining_standard_videos, snapshot_policy


DEFAULTS = {
    'basic': {'allowed': False, 'count': 0, 'size_mb': 0, 'aggregate_mb': 0, 'recording': False},
    'standard': {'allowed': True, 'count': 1, 'size_mb': 80, 'aggregate_mb': 80, 'recording': True},
    'premium': {'allowed': True, 'count': 3, 'size_mb': 200, 'aggregate_mb': 500, 'recording': True},
}


@dataclass(frozen=True)
class VideoUploadPolicy:
    allowed: bool
    plan: str
    max_videos_per_listing: int
    max_video_size_bytes: int
    max_aggregate_video_storage_bytes: int
    allowed_extensions: tuple
    allowed_mime_types: tuple
    max_duration_seconds: int | None
    direct_recording_allowed: bool
    max_video_width: int | None
    max_video_height: int | None
    account_storage_allowance_bytes: int | None
    standard_video_bytes: int
    recommended_duration_seconds: int | None
    soft_max_video_bytes: int
    hard_max_video_size_bytes: int
    maximum_recording_seconds: int | None
    upload_enabled: bool
    recording_enabled: bool
    optimization_enabled: bool
    original_upload_allowed: bool
    original_retention_allowed: bool
    global_capacity: dict
    estimated_remaining_standard_videos: int
    reason: str = ''

    def as_dict(self):
        return {
            'allowed': self.allowed,
            'plan': self.plan,
            'max_videos_per_listing': self.max_videos_per_listing,
            'max_video_size_bytes': self.max_video_size_bytes,
            'max_video_size_mb': self.max_video_size_bytes // (1024 * 1024),
            'max_aggregate_video_storage_bytes': self.max_aggregate_video_storage_bytes,
            'allowed_extensions': list(self.allowed_extensions),
            'allowed_mime_types': list(self.allowed_mime_types),
            'max_duration_seconds': self.max_duration_seconds,
            'direct_recording_allowed': self.direct_recording_allowed,
            'account_storage_allowance_bytes': self.account_storage_allowance_bytes,
            'standard_video_bytes': self.standard_video_bytes,
            'recommended_duration_seconds': self.recommended_duration_seconds,
            'soft_max_video_bytes': self.soft_max_video_bytes,
            'hard_max_video_size_bytes': self.hard_max_video_size_bytes,
            'maximum_recording_seconds': self.maximum_recording_seconds,
            'upload_enabled': self.upload_enabled,
            'recording_enabled': self.recording_enabled,
            'optimization_enabled': self.optimization_enabled,
            'original_upload_allowed': self.original_upload_allowed,
            'original_retention_allowed': self.original_retention_allowed,
            'global_capacity': self.global_capacity,
            'estimated_remaining_standard_videos': self.estimated_remaining_standard_videos,
            'reason': self.reason,
        }


def get_video_upload_policy(user, listing=None):
    global_capacity = snapshot_policy()
    subscription = getattr(user, 'active_subscription', None)
    if not subscription:
        return _policy_from_values('', False, 0, 0, 0, 'Your current plan does not include video uploads.', global_capacity=global_capacity)

    entitlement = VideoPlanEntitlement.objects.filter(plan=subscription.plan).first()
    if entitlement:
        allowance = entitlement.total_video_storage_bytes or ((entitlement.account_storage_allowance_mb or entitlement.max_aggregate_video_storage_mb) * 1024 * 1024)
        allowed = entitlement.video_uploads_allowed and entitlement.upload_enabled and global_capacity.uploads_enabled
        standard_bytes = entitlement.recommended_standard_video_bytes or global_capacity.standard_video_bytes
        return VideoUploadPolicy(
            allowed=allowed,
            plan=subscription.plan,
            max_videos_per_listing=(entitlement.maximum_video_count or entitlement.max_videos_per_listing) if allowed else 0,
            max_video_size_bytes=entitlement.absolute_max_video_bytes if allowed else 0,
            max_aggregate_video_storage_bytes=allowance if allowed else 0,
            allowed_extensions=tuple(entitlement.allowed_extensions_list),
            allowed_mime_types=tuple(entitlement.allowed_mime_types_list),
            max_duration_seconds=entitlement.max_video_duration_seconds or entitlement.maximum_recording_duration_seconds,
            direct_recording_allowed=entitlement.direct_recording_allowed and entitlement.recording_enabled and global_capacity.recording_enabled and allowed,
            max_video_width=entitlement.max_video_width,
            max_video_height=entitlement.max_video_height,
            account_storage_allowance_bytes=allowance or None,
            standard_video_bytes=standard_bytes,
            recommended_duration_seconds=entitlement.recommended_video_duration_seconds,
            soft_max_video_bytes=entitlement.soft_max_video_bytes,
            hard_max_video_size_bytes=entitlement.absolute_max_video_bytes,
            maximum_recording_seconds=entitlement.maximum_recording_duration_seconds,
            upload_enabled=entitlement.upload_enabled and global_capacity.uploads_enabled,
            recording_enabled=entitlement.recording_enabled and global_capacity.recording_enabled,
            optimization_enabled=entitlement.optimization_enabled and global_capacity.optimization_enabled,
            original_upload_allowed=entitlement.original_upload_allowed,
            original_retention_allowed=entitlement.original_retention_allowed,
            global_capacity=global_capacity.as_dict(),
            estimated_remaining_standard_videos=remaining_standard_videos(user, allowance, standard_bytes),
            reason='' if allowed else 'Video uploads are temporarily unavailable. Your existing videos remain available.',
        )

    default = DEFAULTS.get(subscription.plan, DEFAULTS['basic'])
    return _policy_from_values(
        subscription.plan,
        default['allowed'] and global_capacity.uploads_enabled,
        default['count'],
        default['size_mb'],
        default['aggregate_mb'],
        '' if default['allowed'] else 'Your current plan does not include video uploads.',
        default['recording'],
        global_capacity=global_capacity,
        user=user,
    )


def validate_video_upload_request(user, listing, filename, content_type, declared_size):
    policy = get_video_upload_policy(user, listing)
    if not policy.allowed:
        return policy, policy.reason
    if not filename:
        return policy, 'Choose a video file.'
    extension = Path(filename).suffix.lower().lstrip('.')
    if extension not in policy.allowed_extensions:
        return policy, f'Videos must use one of these formats: {", ".join(policy.allowed_extensions)}.'
    if content_type not in policy.allowed_mime_types:
        return policy, f'This video type is not allowed: {content_type or "unknown"}.'
    try:
        size = int(declared_size)
    except (TypeError, ValueError):
        return policy, 'Video size could not be validated.'
    if size <= 0:
        return policy, 'Video size must be greater than zero.'
    if size > policy.max_video_size_bytes:
        return policy, f'Video must be {policy.max_video_size_bytes // (1024 * 1024)} MB or smaller.'
    qs = user.listing_videos.filter(upload_status__in=[ListingVideoStatus.PENDING, ListingVideoStatus.UPLOADING, ListingVideoStatus.PROCESSING, ListingVideoStatus.READY])
    if listing:
        qs = qs.filter(listing=listing)
    else:
        qs = qs.filter(listing__isnull=True)
    if policy.max_videos_per_listing and qs.count() >= policy.max_videos_per_listing:
        return policy, f'Your plan allows {policy.max_videos_per_listing} video(s) per listing.'
    aggregate = qs.aggregate(total=Sum('file_size'))['total'] or 0
    if policy.max_aggregate_video_storage_bytes and aggregate + size > policy.max_aggregate_video_storage_bytes:
        return policy, 'This video needs more space than is currently available. You can optimize it, trim it or manage your existing videos.'
    return policy, ''


def _policy_from_values(plan, allowed, count, size_mb, aggregate_mb, reason, recording=False, global_capacity=None, user=None):
    global_capacity = global_capacity or snapshot_policy()
    allowance = aggregate_mb * 1024 * 1024
    return VideoUploadPolicy(
        allowed=allowed,
        plan=plan,
        max_videos_per_listing=count,
        max_video_size_bytes=size_mb * 1024 * 1024,
        max_aggregate_video_storage_bytes=allowance,
        allowed_extensions=('mp4', 'webm'),
        allowed_mime_types=('video/mp4', 'video/webm'),
        max_duration_seconds=None,
        direct_recording_allowed=recording and allowed and global_capacity.recording_enabled,
        max_video_width=None,
        max_video_height=None,
        account_storage_allowance_bytes=allowance or None,
        standard_video_bytes=global_capacity.standard_video_bytes,
        recommended_duration_seconds=None,
        soft_max_video_bytes=size_mb * 1024 * 1024,
        hard_max_video_size_bytes=size_mb * 1024 * 1024,
        maximum_recording_seconds=None,
        upload_enabled=allowed and global_capacity.uploads_enabled,
        recording_enabled=recording and allowed and global_capacity.recording_enabled,
        optimization_enabled=global_capacity.optimization_enabled,
        original_upload_allowed=True,
        original_retention_allowed=False,
        global_capacity=global_capacity.as_dict(),
        estimated_remaining_standard_videos=remaining_standard_videos(user, allowance, global_capacity.standard_video_bytes) if user else 0,
        reason=reason,
    )
