from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


class AccountRole(models.TextChoices):
    SEEKER = 'seeker', 'Seeker'           # students / house hunters
    LANDLORD = 'landlord', 'Landlord'     # rental property owners
    SME = 'sme', 'SME Seller'            # small business sellers
    AUTO = 'auto', 'Auto Dealer'          # automotive dealers
    ADMIN = 'admin', 'Administrator'


class VerificationStatus(models.TextChoices):
    UNVERIFIED = 'unverified', 'Unverified'
    PENDING = 'pending', 'Pending Review'
    VERIFIED = 'verified', 'Verified'
    REJECTED = 'rejected', 'Rejected'


class CustomUser(AbstractUser):
    """
    Extended user model for NyumbaHub.
    Role determines which features and forms the user sees.
    """
    email = models.EmailField(unique=True)
    phone = PhoneNumberField(region='TZ', blank=True, null=True, unique=True)
    role = models.CharField(
        max_length=20,
        choices=AccountRole.choices,
        default=AccountRole.SEEKER,
    )
    bio = models.TextField(blank=True, max_length=500)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    location = models.CharField(max_length=120, blank=True)  # city / district
    shop_name = models.CharField(max_length=120, blank=True)
    shop_location = models.CharField(max_length=160, blank=True)
    nearby_names = models.CharField(max_length=240, blank=True)
    public_phone = PhoneNumberField(region='TZ', blank=True, null=True)
    whatsapp_phone = PhoneNumberField(region='TZ', blank=True, null=True)
    website_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)

    # Verification
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    # Flags
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    receives_notifications = models.BooleanField(default=True)
    receives_push_notifications = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    @property
    def is_provider(self):
        """True for any account that can post listings."""
        return self.role in [AccountRole.LANDLORD, AccountRole.SME, AccountRole.AUTO]

    @property
    def is_seeker(self):
        return self.role == AccountRole.SEEKER

    @property
    def is_verified(self):
        return self.verification_status == VerificationStatus.VERIFIED

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def verification_badge_label(self):
        """Public wording backed exclusively by the persisted KYC status."""
        if not self.is_verified:
            return ''
        return {
            AccountRole.SME: 'Verified Business',
            AccountRole.LANDLORD: 'Verified Property Lister',
            AccountRole.AUTO: 'Verified Dealer',
        }.get(self.role, '')

    @property
    def active_subscription(self):
        return self.subscriptions.filter(is_active=True).first()

    @property
    def can_post_listing(self):
        if not self.is_provider:
            return False
        sub = self.active_subscription
        if not sub:
            return False
        return sub.listings_remaining > 0


class KYCDocument(models.Model):
    """
    Landlord / provider identity verification documents.
    Admin reviews these manually and approves/rejects the user.
    Scaffold is in place — enforcement can be activated in settings.
    """
    class DocType(models.TextChoices):
        NATIONAL_ID = 'national_id', 'National ID'
        PASSPORT = 'passport', 'Passport'
        DRIVERS_LICENSE = 'drivers_license', "Driver's License"
        UTILITY_BILL = 'utility_bill', 'Utility Bill'

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='kyc',
    )
    doc_type = models.CharField(max_length=30, choices=DocType.choices)
    document_front = models.ImageField(upload_to='kyc/docs/')
    document_back = models.ImageField(upload_to='kyc/docs/', blank=True, null=True)
    selfie = models.ImageField(upload_to='kyc/selfies/', blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )
    admin_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'KYC Document'
        verbose_name_plural = 'KYC Documents'

    def __str__(self):
        return f"KYC: {self.user.email} — {self.status}"
