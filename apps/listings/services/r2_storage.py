from pathlib import Path
from uuid import uuid4

from django.conf import settings

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    Config = None
    ClientError = Exception


def r2_configured():
    return bool(settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY and settings.R2_BUCKET_NAME and settings.R2_ENDPOINT_URL and boto3)


def make_video_object_key(owner_id, listing_id, filename):
    extension = Path(filename).suffix.lower()
    if extension not in {'.mp4', '.webm'}:
        extension = ''
    listing_part = str(listing_id) if listing_id else 'pending'
    prefix = settings.R2_VIDEO_PREFIX.strip('/') + '/'
    return f'{prefix}owner-{owner_id}/listing-{listing_part}/{uuid4().hex}{extension}'


def create_presigned_upload(video):
    _require_configured()
    client = _client()
    fields = {'Content-Type': video.content_type}
    conditions = [
        {'Content-Type': video.content_type},
        ['content-length-range', 1, video.file_size],
    ]
    return client.generate_presigned_post(
        Bucket=settings.R2_BUCKET_NAME,
        Key=video.object_key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=settings.R2_UPLOAD_URL_EXPIRY_SECONDS,
    )


def create_presigned_playback_url(video):
    if _public_base_url():
        return f'{_public_base_url()}/{video.object_key}'
    _require_configured()
    return _client().generate_presigned_url(
        'get_object',
        Params={'Bucket': settings.R2_BUCKET_NAME, 'Key': video.object_key},
        ExpiresIn=settings.R2_SIGNED_URL_EXPIRY_SECONDS,
    )


def verify_uploaded_object(video):
    _require_configured()
    try:
        metadata = _client().head_object(Bucket=settings.R2_BUCKET_NAME, Key=video.object_key)
    except ClientError:
        return False, {}
    size = int(metadata.get('ContentLength') or 0)
    content_type = metadata.get('ContentType') or ''
    return size == video.file_size and content_type.split(';')[0] == video.content_type, {
        'content_length': size,
        'content_type': content_type,
        'etag': metadata.get('ETag', '').strip('"'),
    }


def object_exists(video):
    if not r2_configured():
        return None
    try:
        _client().head_object(Bucket=settings.R2_BUCKET_NAME, Key=video.object_key)
        return True
    except ClientError:
        return False


def delete_object(video):
    if not r2_configured():
        return False
    _client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=video.object_key)
    return True


def _client():
    return boto3.client(
        's3',
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name=settings.R2_REGION,
        config=Config(signature_version='s3v4'),
    )


def _public_base_url():
    if settings.R2_VIDEO_DELIVERY_MODE == 'public':
        return (settings.R2_CUSTOM_DOMAIN or settings.R2_PUBLIC_BASE_URL).rstrip('/')
    return ''


def _require_configured():
    if not r2_configured():
        raise RuntimeError('Cloudflare R2 video storage is not configured.')
