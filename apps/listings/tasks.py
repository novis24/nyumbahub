from celery import shared_task

from apps.listings.services.video_quota import expire_stale_reservations


@shared_task
def expire_video_upload_reservations():
    return expire_stale_reservations()
