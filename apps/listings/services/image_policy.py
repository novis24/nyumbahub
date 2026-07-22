import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

ALLOWED_FORMATS = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'WEBP': 'image/webp',
}
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_PIXELS = 25_000_000


def max_image_upload_bytes():
    return getattr(settings, 'LISTING_IMAGE_MAX_UPLOAD_BYTES', DEFAULT_MAX_BYTES)


def max_image_pixels():
    return getattr(settings, 'LISTING_IMAGE_MAX_PIXELS', DEFAULT_MAX_PIXELS)


def validate_listing_image(uploaded_file):
    if not uploaded_file or not getattr(uploaded_file, 'size', 0):
        raise ValidationError(_('Upload a valid image file.'))

    max_bytes = max_image_upload_bytes()
    if uploaded_file.size > max_bytes:
        limit_mb = max(1, round(max_bytes / (1024 * 1024)))
        raise ValidationError(_('Each image must be %(limit)s MB or smaller.') % {'limit': limit_mb})

    initial_position = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else 0
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image.verify()
            image_format = image.format

        if image_format not in ALLOWED_FORMATS:
            raise ValidationError(_('Unsupported image format. Please upload JPEG, PNG, or WebP images.'))

        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValidationError(_('Upload a valid image file.'))
            if width * height > max_image_pixels():
                raise ValidationError(_('This image is too large. Please upload a smaller photo.'))
            image.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError(_('This image could not be read. Please upload JPEG, PNG, or WebP images.'))
    finally:
        try:
            uploaded_file.seek(initial_position)
        except (AttributeError, OSError):
            pass


def validate_listing_images(uploaded_files):
    for uploaded_file in uploaded_files:
        validate_listing_image(uploaded_file)
