from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, KYCDocument
from apps.listings.models import Listing, ListingImage, SavedListing
from apps.subscriptions.models import Subscription, PaymentLog
from apps.notifications.models import Notification


# ─── Accounts ─────────────────────────────────────────────

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'get_full_name', 'role', 'verification_status', 'is_active', 'date_joined')
    list_filter = ('role', 'verification_status', 'is_active')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('NyumbaHub', {
            'fields': ('role', 'phone', 'bio', 'avatar', 'location',
                       'verification_status', 'verified_at',
                       'is_phone_verified', 'is_email_verified',
                       'receives_notifications'),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('NyumbaHub', {
            'fields': ('email', 'role', 'phone'),
        }),
    )

    # Quick action: approve verification
    actions = ['approve_verification', 'reject_verification']

    @admin.action(description='Approve verification for selected users')
    def approve_verification(self, request, queryset):
        from django.utils import timezone
        queryset.update(
            verification_status='verified',
            verified_at=timezone.now(),
        )
        # Also update KYC if present
        for user in queryset:
            if hasattr(user, 'kyc'):
                user.kyc.status = 'verified'
                user.kyc.save(update_fields=['status'])

    @admin.action(description='Reject verification for selected users')
    def reject_verification(self, request, queryset):
        queryset.update(verification_status='rejected')


@admin.register(KYCDocument)
class KYCDocumentAdmin(admin.ModelAdmin):
    list_display = ('user', 'doc_type', 'status', 'submitted_at', 'reviewed_at')
    list_filter = ('status', 'doc_type')
    search_fields = ('user__email', 'user__first_name')
    readonly_fields = ('submitted_at',)
    raw_id_fields = ('user',)


# ─── Listings ─────────────────────────────────────────────

class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0
    fields = ('image', 'is_cover', 'order', 'caption')


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'listing_type', 'status', 'owner', 'city', 'price', 'is_featured', 'created_at')
    list_filter = ('listing_type', 'status', 'is_featured', 'city')
    search_fields = ('title', 'owner__email', 'location', 'city')
    list_editable = ('is_featured', 'status')
    raw_id_fields = ('owner',)
    inlines = [ListingImageInline]
    readonly_fields = ('slug', 'views_count', 'created_at', 'updated_at')

    actions = ['activate_listings', 'pause_listings', 'feature_listings']

    @admin.action(description='Activate selected listings')
    def activate_listings(self, request, queryset):
        queryset.update(status='active')

    @admin.action(description='Pause selected listings')
    def pause_listings(self, request, queryset):
        queryset.update(status='paused')

    @admin.action(description='Toggle featured on selected listings')
    def feature_listings(self, request, queryset):
        for l in queryset:
            l.is_featured = not l.is_featured
            l.save(update_fields=['is_featured'])


# ─── Subscriptions ────────────────────────────────────────

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'is_active', 'started_at', 'expires_at', 'amount_paid_tzs')
    list_filter = ('plan', 'is_active')
    search_fields = ('user__email',)
    raw_id_fields = ('user',)
    list_editable = ('is_active',)
    readonly_fields = ('started_at',)


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount_tzs', 'method', 'status', 'created_at')
    list_filter = ('status', 'method')
    search_fields = ('user__email', 'reference')
    readonly_fields = ('created_at',)


# ─── Notifications ────────────────────────────────────────

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('user__email', 'title')
    raw_id_fields = ('user',)
