from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms
from .models import CustomUser, KYCDocument
from apps.listings.models import (
    GlobalVideoStorageAudit,
    GlobalVideoStoragePolicy,
    Listing,
    ListingImage,
    ListingVideo,
    ListingVideoStatus,
    SavedListing,
    VideoUploadReservation,
)
from apps.listings.services.r2_storage import object_exists
from apps.subscriptions.models import Subscription, PaymentLog, VideoPlanEntitlement
from apps.notifications.models import Notification


class GlobalVideoStoragePolicyForm(forms.ModelForm):
    global_storage_cap_gb = forms.DecimalField(label='Global storage cap (GB)', min_value=0, decimal_places=2, required=True)
    change_reason = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    confirm_over_capacity = forms.BooleanField(required=False, label='Confirm over-capacity state')

    class Meta:
        model = GlobalVideoStoragePolicy
        fields = (
            'global_storage_cap_gb',
            'uploads_enabled',
            'recording_enabled',
            'optimization_enabled',
            'standard_video_bytes',
            'recommended_duration_seconds',
            'soft_video_size_bytes',
            'hard_video_size_bytes',
            'maximum_recording_seconds',
            'temporary_object_lifetime_minutes',
            'warning_threshold_percent',
            'critical_threshold_percent',
            'target_video_height',
            'target_frame_rate',
            'original_retention_enabled',
            'last_known_r2_usage_bytes',
            'reconciliation_status',
            'change_reason',
            'confirm_over_capacity',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['global_storage_cap_gb'].initial = self.instance.global_storage_cap_bytes / 1_000_000_000

    def clean(self):
        cleaned = super().clean()
        cap_gb = cleaned.get('global_storage_cap_gb')
        if cap_gb is not None:
            cap_bytes = int(cap_gb * 1_000_000_000)
            cleaned['global_storage_cap_bytes'] = cap_bytes
            current_usage = int((self.instance.committed_bytes or 0) + (self.instance.reserved_bytes or 0))
            if cap_bytes < current_usage and not cleaned.get('confirm_over_capacity'):
                raise forms.ValidationError('The cap is below committed plus reserved video usage. Confirm the over-capacity state to save it.')
        return cleaned

    def save(self, commit=True):
        self.instance.global_storage_cap_bytes = self.cleaned_data['global_storage_cap_bytes']
        return super().save(commit=commit)


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


class ListingVideoInline(admin.TabularInline):
    model = ListingVideo
    extra = 0
    fields = ('owner', 'upload_status', 'original_filename', 'content_type', 'file_size', 'order', 'moderation_state', 'created_at', 'completed_at')
    readonly_fields = ('owner', 'upload_status', 'original_filename', 'content_type', 'file_size', 'created_at', 'completed_at')
    can_delete = False


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'listing_type', 'status', 'owner', 'city', 'price', 'is_featured', 'created_at')
    list_filter = ('listing_type', 'status', 'is_featured', 'city')
    search_fields = ('title', 'owner__email', 'location', 'city')
    list_editable = ('is_featured', 'status')
    raw_id_fields = ('owner',)
    inlines = [ListingImageInline, ListingVideoInline]
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


@admin.register(ListingVideo)
class ListingVideoAdmin(admin.ModelAdmin):
    list_display = ('listing', 'owner', 'upload_status', 'content_type', 'file_size', 'created_at', 'ready', 'r2_object_exists')
    list_filter = ('upload_status', 'content_type', 'moderation_state', 'cleanup_required')
    search_fields = ('listing__title', 'owner__email', 'object_key', 'original_filename')
    readonly_fields = ('id', 'object_key', 'upload_id', 'created_at', 'updated_at', 'completed_at', 'r2_object_exists')
    raw_id_fields = ('listing', 'owner')

    @admin.display(boolean=True)
    def ready(self, obj):
        return obj.upload_status == ListingVideoStatus.READY

    @admin.display(description='R2 object exists')
    def r2_object_exists(self, obj):
        exists = object_exists(obj)
        if exists is None:
            return 'R2 not configured'
        return 'Yes' if exists else 'No'


@admin.register(GlobalVideoStoragePolicy)
class GlobalVideoStoragePolicyAdmin(admin.ModelAdmin):
    form = GlobalVideoStoragePolicyForm
    list_display = ('__str__', 'global_storage_cap_bytes', 'committed_bytes', 'reserved_bytes', 'available_capacity', 'percent_consumed', 'uploads_enabled', 'recording_enabled', 'optimization_enabled')
    readonly_fields = (
        'committed_bytes',
        'reserved_bytes',
        'available_capacity',
        'percent_consumed',
        'temporary_object_usage',
        'active_uploads',
        'failed_uploads',
        'orphaned_objects',
        'last_reconciled_at',
        'updated_by',
        'updated_at',
    )
    fieldsets = (
        ('System Administration > Video Storage & Processing', {
            'fields': ('global_storage_cap_gb', 'change_reason', 'confirm_over_capacity', 'uploads_enabled', 'recording_enabled', 'optimization_enabled')
        }),
        ('Usage', {
            'fields': ('committed_bytes', 'reserved_bytes', 'available_capacity', 'percent_consumed', 'last_known_r2_usage_bytes', 'temporary_object_usage', 'active_uploads', 'failed_uploads', 'orphaned_objects', 'last_reconciled_at', 'reconciliation_status')
        }),
        ('Processing Policy', {
            'fields': ('standard_video_bytes', 'recommended_duration_seconds', 'soft_video_size_bytes', 'hard_video_size_bytes', 'maximum_recording_seconds', 'temporary_object_lifetime_minutes', 'warning_threshold_percent', 'critical_threshold_percent', 'target_video_height', 'target_frame_rate', 'original_retention_enabled')
        }),
        ('Audit', {'fields': ('updated_by', 'updated_at')}),
    )

    def has_add_permission(self, request):
        return not GlobalVideoStoragePolicy.objects.exists() and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        old_value = None
        if change:
            old_value = GlobalVideoStoragePolicy.objects.get(pk=obj.pk).global_storage_cap_bytes
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
        if old_value is not None and old_value != obj.global_storage_cap_bytes:
            GlobalVideoStorageAudit.objects.create(
                policy=obj,
                old_value=old_value,
                new_value=obj.global_storage_cap_bytes,
                administrator=request.user,
                reason=form.cleaned_data.get('change_reason', ''),
            )

    @admin.display(description='Available capacity')
    def available_capacity(self, obj):
        return obj.available_bytes

    @admin.display(description='Temporary-object usage')
    def temporary_object_usage(self, obj):
        return VideoUploadReservation.objects.filter(status__in=['uploading', 'uploaded_temporarily', 'queued', 'processing']).count()

    @admin.display(description='Active uploads')
    def active_uploads(self, obj):
        return VideoUploadReservation.objects.filter(status__in=['reserved', 'uploading', 'uploaded_temporarily', 'queued', 'processing']).count()

    @admin.display(description='Failed uploads')
    def failed_uploads(self, obj):
        return VideoUploadReservation.objects.filter(status__in=['failed', 'rejected', 'expired']).count()

    @admin.display(description='Orphaned objects')
    def orphaned_objects(self, obj):
        return ListingVideo.objects.filter(cleanup_required=True).count()


@admin.register(VideoUploadReservation)
class VideoUploadReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'listing', 'status', 'declared_size', 'reserved_temporary_bytes', 'reserved_final_bytes', 'created_at', 'expiration_time')
    list_filter = ('status',)
    search_fields = ('user__email', 'listing__title', 'object_key')
    readonly_fields = [field.name for field in VideoUploadReservation._meta.fields]


@admin.register(GlobalVideoStorageAudit)
class GlobalVideoStorageAuditAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'old_value', 'new_value', 'administrator', 'created_at')
    search_fields = ('administrator__email', 'reason')
    readonly_fields = [field.name for field in GlobalVideoStorageAudit._meta.fields]


# ─── Subscriptions ────────────────────────────────────────

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'is_active', 'started_at', 'expires_at', 'amount_paid_tzs')
    list_filter = ('plan', 'is_active')
    search_fields = ('user__email',)
    raw_id_fields = ('user',)
    list_editable = ('is_active',)
    readonly_fields = ('started_at',)


@admin.register(VideoPlanEntitlement)
class VideoPlanEntitlementAdmin(admin.ModelAdmin):
    list_display = ('plan', 'video_uploads_allowed', 'max_videos_per_listing', 'max_video_size_mb', 'max_aggregate_video_storage_mb', 'direct_recording_allowed')
    list_filter = ('video_uploads_allowed', 'direct_recording_allowed')


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
