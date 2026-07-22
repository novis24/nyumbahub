from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid


class Plan(models.TextChoices):
    BASIC = 'basic', 'Basic'
    STANDARD = 'standard', 'Standard'
    PREMIUM = 'premium', 'Premium'


class Subscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )
    plan = models.CharField(max_length=20, choices=Plan.choices)
    is_active = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)

    # Payment reference
    payment_reference = models.CharField(max_length=120, blank=True)
    amount_paid_tzs = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user.email} — {self.plan} ({'active' if self.is_active else 'inactive'})"

    @property
    def limits(self):
        return settings.PLAN_LIMITS.get(self.plan, {})

    @property
    def max_listings(self):
        return self.limits.get('listings', 0)

    @property
    def max_images(self):
        return self.limits.get('images_per_listing', 3)

    @property
    def listings_used(self):
        return self.user.listings.filter(status='active').count()

    @property
    def listings_remaining(self):
        return max(0, self.max_listings - self.listings_used)

    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at


class VideoPlanEntitlement(models.Model):
    plan = models.CharField(max_length=20, choices=Plan.choices, unique=True)
    video_uploads_allowed = models.BooleanField(default=False)
    max_videos_per_listing = models.PositiveSmallIntegerField(default=0)
    max_video_size_mb = models.PositiveIntegerField(default=0)
    max_aggregate_video_storage_mb = models.PositiveIntegerField(default=0)
    allowed_video_extensions = models.CharField(max_length=160, default='mp4,webm')
    allowed_video_mime_types = models.CharField(max_length=240, default='video/mp4,video/webm')
    max_video_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    direct_recording_allowed = models.BooleanField(default=False)
    max_video_width = models.PositiveIntegerField(null=True, blank=True)
    max_video_height = models.PositiveIntegerField(null=True, blank=True)
    account_storage_allowance_mb = models.PositiveIntegerField(null=True, blank=True)
    total_video_storage_bytes = models.PositiveBigIntegerField(default=0)
    recommended_standard_video_bytes = models.PositiveBigIntegerField(default=50_000_000)
    recommended_video_duration_seconds = models.PositiveIntegerField(default=60)
    soft_max_video_bytes = models.PositiveBigIntegerField(default=50_000_000)
    absolute_max_video_bytes = models.PositiveBigIntegerField(default=200_000_000)
    maximum_recording_duration_seconds = models.PositiveIntegerField(default=120)
    maximum_video_count = models.PositiveIntegerField(null=True, blank=True)
    recording_enabled = models.BooleanField(default=True)
    upload_enabled = models.BooleanField(default=True)
    optimization_enabled = models.BooleanField(default=True)
    original_upload_allowed = models.BooleanField(default=True)
    original_retention_allowed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['plan']

    def clean(self):
        hard_limit = getattr(settings, 'R2_VIDEO_MAX_SIZE_HARD_LIMIT_MB', 500)
        if self.max_video_size_mb > hard_limit:
            raise ValidationError({'max_video_size_mb': f'Maximum size cannot exceed {hard_limit} MB.'})
        if not self.video_uploads_allowed:
            return
        if self.max_videos_per_listing < 1:
            raise ValidationError({'max_videos_per_listing': 'Allow at least one video or disable video uploads.'})
        if self.max_video_size_mb < 1:
            raise ValidationError({'max_video_size_mb': 'Set a positive per-video size.'})
        if self.max_aggregate_video_storage_mb and self.max_aggregate_video_storage_mb < self.max_video_size_mb:
            raise ValidationError({'max_aggregate_video_storage_mb': 'Aggregate listing storage must be at least the per-video size.'})

    def save(self, *args, **kwargs):
        self.allowed_video_extensions = _normalize_csv(self.allowed_video_extensions, strip_dot=True)
        self.allowed_video_mime_types = _normalize_csv(self.allowed_video_mime_types)
        mb = 1024 * 1024
        if self.max_aggregate_video_storage_mb and not self.total_video_storage_bytes:
            self.total_video_storage_bytes = self.max_aggregate_video_storage_mb * mb
        if self.max_video_size_mb and self.absolute_max_video_bytes == 200_000_000:
            self.absolute_max_video_bytes = self.max_video_size_mb * mb
        if self.max_video_size_mb and self.soft_max_video_bytes == 50_000_000:
            self.soft_max_video_bytes = min(self.max_video_size_mb * mb, self.soft_max_video_bytes)
        if self.max_videos_per_listing and self.maximum_video_count is None:
            self.maximum_video_count = self.max_videos_per_listing
        if self.max_video_duration_seconds and self.maximum_recording_duration_seconds == 120:
            self.maximum_recording_duration_seconds = self.max_video_duration_seconds
        self.direct_recording_allowed = self.direct_recording_allowed and self.recording_enabled
        self.video_uploads_allowed = self.video_uploads_allowed and self.upload_enabled
        super().save(*args, **kwargs)

    @property
    def allowed_extensions_list(self):
        return [value for value in self.allowed_video_extensions.split(',') if value]

    @property
    def allowed_mime_types_list(self):
        return [value for value in self.allowed_video_mime_types.split(',') if value]

    def __str__(self):
        return f'{self.get_plan_display()} video limits'


def _normalize_csv(value, strip_dot=False):
    items = []
    for raw in (value or '').split(','):
        item = raw.strip().lower()
        if strip_dot:
            item = item.lstrip('.')
        if item and item not in items:
            items.append(item)
    return ','.join(items)


class PaymentLog(models.Model):
    """Audit trail for all payment attempts."""
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payment_logs',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_logs',
    )
    amount_tzs = models.DecimalField(max_digits=12, decimal_places=0)
    method = models.CharField(max_length=30)   # 'mpesa', 'card', etc.
    reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — {self.amount_tzs} TZS ({self.status})"
