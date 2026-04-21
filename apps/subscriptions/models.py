from django.db import models
from django.conf import settings
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
