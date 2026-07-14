from django.db import models
from django.conf import settings


class NotificationType(models.TextChoices):
    LISTING_APPROVED = 'listing_approved', 'Listing Approved'
    LISTING_EXPIRED = 'listing_expired', 'Listing Expired'
    SUBSCRIPTION_EXPIRING = 'sub_expiring', 'Subscription Expiring'
    SUBSCRIPTION_RENEWED = 'sub_renewed', 'Subscription Renewed'
    KYC_APPROVED = 'kyc_approved', 'Verification Approved'
    KYC_REJECTED = 'kyc_rejected', 'Verification Rejected'
    NEW_INQUIRY = 'new_inquiry', 'New Inquiry'
    SYSTEM = 'system', 'System Message'
    NEW_MARKET_LISTING = 'new_market_listing', 'New Marketplace Listing'


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
    )
    title = models.CharField(max_length=120)
    body = models.TextField(blank=True)
    action_url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} — {self.title}"

    @classmethod
    def send(cls, user, notification_type, title, body='', action_url=''):
        if user.receives_notifications:
            return cls.objects.create(
                user=user,
                notification_type=notification_type,
                title=title,
                body=body,
                action_url=action_url,
            )


class PushDevice(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='push_devices'
    )
    token = models.TextField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.email} device'
