from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Avg
from django.utils.text import slugify
from collections import Counter
import uuid
from decimal import Decimal


class ListingType(models.TextChoices):
    RENTAL = 'rental', 'Rental Property'
    SME = 'sme', 'SME / Business'
    AUTO = 'auto', 'Automotive'


class ListingStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    ACTIVE = 'active', 'Active'
    PAUSED = 'paused', 'Paused'
    EXPIRED = 'expired', 'Expired'
    SOLD = 'sold', 'Sold / Rented'


class PropertyType(models.TextChoices):
    SINGLE_ROOM = 'single_room', 'Single Room'
    SELF_CONTAINED = 'self_contained', 'Self Contained'
    BEDSITTER = 'bedsitter', 'Bedsitter'
    ONE_BEDROOM = '1_bedroom', '1 Bedroom'
    TWO_BEDROOM = '2_bedroom', '2 Bedrooms'
    THREE_BEDROOM = '3_bedroom', '3 Bedrooms'
    FOUR_PLUS = '4_plus', '4+ Bedrooms'
    STUDIO = 'studio', 'Studio'
    SHARED = 'shared', 'Shared House'
    HOSTEL = 'hostel', 'Hostel / Student'


class LocationPrecision(models.TextChoices):
    EXACT = 'exact', 'Show exact location'
    APPROXIMATE = 'approximate', 'Show approximate area'


class ProductCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='subcategories')
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'SME product category'
        verbose_name_plural = 'SME product categories'

    def __str__(self):
        return f'{self.parent.name} / {self.name}' if self.parent else self.name


class ProductAttribute(models.Model):
    category = models.ForeignKey(ProductCategory, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100)
    input_type = models.CharField(max_length=20, choices=[('text', 'Text'), ('number', 'Number'), ('choice', 'Choice')], default='text')
    choices = models.CharField(max_length=500, blank=True, help_text='Comma-separated choices for choice fields.')
    is_filterable = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']
        unique_together = ('category', 'slug')

    def __str__(self):
        return f'{self.category}: {self.name}'


class Listing(models.Model):
    """
    Single unified listing model.
    listing_type controls which fields are relevant.
    The admin and template layer shows only the fields that matter
    for each type — progressive disclosure at the data level.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listings',
    )
    listing_type = models.CharField(max_length=10, choices=ListingType.choices)
    status = models.CharField(
        max_length=10,
        choices=ListingStatus.choices,
        default=ListingStatus.DRAFT,
    )

    # ── Core fields (all types) ────────────────────────
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(max_length=2000)
    price = models.DecimalField(max_digits=12, decimal_places=0)  # TZS, no decimals
    location = models.CharField(max_length=120)  # District / area
    city = models.CharField(max_length=60, default='Dar es Salaam')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    nearby_landmark = models.CharField(max_length=160, blank=True)
    location_precision = models.CharField(
        max_length=12, choices=LocationPrecision.choices, default=LocationPrecision.APPROXIMATE
    )
    is_featured = models.BooleanField(default=False)
    views_count = models.PositiveIntegerField(default=0)

    # ── Rental-specific fields ─────────────────────────
    property_type = models.CharField(
        max_length=20,
        choices=PropertyType.choices,
        blank=True,
    )
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    floor_number = models.PositiveSmallIntegerField(null=True, blank=True)
    is_furnished = models.BooleanField(default=False)
    allows_students = models.BooleanField(default=False)

    # Amenities stored as a simple comma-separated string
    # e.g. "wifi,water,security,parking"
    amenities = models.CharField(max_length=255, blank=True)

    # ── SME-specific ───────────────────────────────────
    business_category = models.CharField(max_length=80, blank=True)
    product_category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.PROTECT, related_name='listings')
    product_subcategory = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.PROTECT, related_name='subcategory_listings')
    product_attributes = models.JSONField(default=dict, blank=True)
    is_for_sale = models.BooleanField(default=False)  # sale vs rent for commercial

    # ── Auto-specific ──────────────────────────────────
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=60, blank=True)
    vehicle_year = models.PositiveSmallIntegerField(null=True, blank=True)
    mileage_km = models.PositiveIntegerField(null=True, blank=True)

    # ── Timestamps ────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-is_featured', '-created_at']
        indexes = [
            models.Index(fields=['listing_type', 'status']),
            models.Index(fields=['city', 'status']),
            models.Index(fields=['is_featured', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            self.slug = f"{base}-{str(self.id)[:8]}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('listings:detail', kwargs={'slug': self.slug})

    @property
    def amenities_list(self):
        if not self.amenities:
            return []
        return [a.strip() for a in self.amenities.split(',') if a.strip()]

    @property
    def cover_image(self):
        img = self.images.filter(is_cover=True).first()
        if not img:
            img = self.images.first()
        return img

    @property
    def price_display(self):
        """Returns formatted TZS price string."""
        return f"TZS {int(self.price):,}"

    @property
    def price_per_month(self):
        if self.listing_type == ListingType.RENTAL:
            return f"{self.price_display}/mo"
        return self.price_display

    @property
    def verification_badge_label(self):
        return self.owner.verification_badge_label

    @property
    def has_public_map(self):
        return self.listing_type == ListingType.RENTAL and self.latitude is not None and self.longitude is not None

    @property
    def public_latitude(self):
        if not self.has_public_map:
            return None
        if self.location_precision == LocationPrecision.EXACT:
            return self.latitude
        # Deterministic coarse position (~1.1km grid): never serialize the exact value.
        return self.latitude.quantize(Decimal('0.01'))

    @property
    def public_longitude(self):
        if not self.has_public_map:
            return None
        if self.location_precision == LocationPrecision.EXACT:
            return self.longitude
        return self.longitude.quantize(Decimal('0.01'))

    def _review_ratings(self):
        cached_reviews = getattr(self, '_prefetched_objects_cache', {}).get('reviews')
        if cached_reviews is not None:
            return [review.rating for review in cached_reviews]
        return list(self.reviews.values_list('rating', flat=True))

    @property
    def likes_count(self):
        return self.saved_by.count()

    @property
    def reviews_count(self):
        return len(self._review_ratings())

    @property
    def average_rating(self):
        ratings = self._review_ratings()
        if ratings:
            return sum(ratings) / len(ratings)
        stats = self.reviews.aggregate(avg=Avg('rating'))
        return stats['avg'] or 0

    @property
    def dominant_rating(self):
        ratings = self._review_ratings()
        if not ratings:
            return 0
        counts = Counter(ratings)
        dominant, _ = max(counts.items(), key=lambda item: (item[1], item[0]))
        return dominant

    @property
    def dominant_rating_count(self):
        ratings = self._review_ratings()
        if not ratings:
            return 0
        counts = Counter(ratings)
        dominant, count = max(counts.items(), key=lambda item: (item[1], item[0]))
        return count

    @property
    def has_client_reviews(self):
        return self.reviews_count > 0


class ListingImage(models.Model):
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='listings/')
    is_cover = models.BooleanField(default=False)
    caption = models.CharField(max_length=120, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', '-is_cover']

    def __str__(self):
        return f"Image for {self.listing.title}"


class HeroGroup(models.Model):
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    rotation_seconds = models.PositiveSmallIntegerField(default=8)
    group_duration_seconds = models.PositiveSmallIntegerField(default=40)
    eyebrow = models.CharField(max_length=120, blank=True)
    headline = models.CharField(max_length=160, blank=True)
    subheading = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class HeroImage(models.Model):
    group = models.ForeignKey(HeroGroup, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='hero/')
    alt_text = models.CharField(max_length=120, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def clean(self):
        from django.core.exceptions import ValidationError
        siblings = HeroImage.objects.filter(group=self.group)
        if self.pk:
            siblings = siblings.exclude(pk=self.pk)
        if self.group_id and siblings.count() >= 5:
            raise ValidationError('A hero group can contain a maximum of five images.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group.name} image {self.order + 1}"


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name='sme_cart')
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['session_key'])]


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('cart', 'listing')

    @property
    def line_total(self):
        return self.listing.price * self.quantity


class SMEOrder(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        CONFIRMED = 'confirmed', 'Confirmed'
        CANCELLED = 'cancelled', 'Cancelled'

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='sme_orders')
    access_key = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=40)
    customer_email = models.EmailField(blank=True)
    fulfillment_method = models.CharField(max_length=20, choices=[('delivery', 'Delivery'), ('pickup', 'Collection')], default='delivery')
    delivery_location = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    total = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class SMEOrderItem(models.Model):
    order = models.ForeignKey(SMEOrder, on_delete=models.CASCADE, related_name='items')
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sme_order_items')
    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name='order_items')
    title = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=12, decimal_places=0)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=12, decimal_places=0)



class ListingVideoStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    UPLOADING = 'uploading', 'Uploading'
    PROCESSING = 'processing', 'Processing'
    READY = 'ready', 'Ready'
    FAILED = 'failed', 'Failed'
    DELETED = 'deleted', 'Deleted'


class VideoReservationStatus(models.TextChoices):
    RESERVED = 'reserved', 'Reserved'
    UPLOADING = 'uploading', 'Uploading'
    UPLOADED_TEMPORARILY = 'uploaded_temporarily', 'Uploaded temporarily'
    QUEUED = 'queued', 'Queued'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    EXPIRED = 'expired', 'Expired'
    REJECTED = 'rejected', 'Rejected'
    FAILED = 'failed', 'Failed'
    DELETING = 'deleting', 'Deleting'
    DELETED = 'deleted', 'Deleted'


class GlobalVideoStoragePolicy(models.Model):
    global_storage_cap_bytes = models.PositiveBigIntegerField()
    committed_bytes = models.PositiveBigIntegerField(default=0)
    reserved_bytes = models.PositiveBigIntegerField(default=0)
    uploads_enabled = models.BooleanField(default=True)
    recording_enabled = models.BooleanField(default=True)
    optimization_enabled = models.BooleanField(default=True)
    standard_video_bytes = models.PositiveBigIntegerField(default=50_000_000)
    recommended_duration_seconds = models.PositiveIntegerField(default=60)
    soft_video_size_bytes = models.PositiveBigIntegerField(default=50_000_000)
    hard_video_size_bytes = models.PositiveBigIntegerField(default=200_000_000)
    maximum_recording_seconds = models.PositiveIntegerField(default=120)
    temporary_object_lifetime_minutes = models.PositiveIntegerField(default=60)
    warning_threshold_percent = models.PositiveSmallIntegerField(default=80)
    critical_threshold_percent = models.PositiveSmallIntegerField(default=95)
    target_video_height = models.PositiveIntegerField(default=720)
    target_frame_rate = models.PositiveIntegerField(default=30)
    original_retention_enabled = models.BooleanField(default=False)
    last_known_r2_usage_bytes = models.PositiveBigIntegerField(default=0)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    reconciliation_status = models.CharField(max_length=40, default='never_run')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Video Storage & Processing'
        verbose_name_plural = 'Video Storage & Processing'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        from django.conf import settings
        return cls.objects.get_or_create(
            pk=1,
            defaults={'global_storage_cap_bytes': settings.VIDEO_GLOBAL_STORAGE_CAP_BYTES},
        )[0]

    @property
    def consumed_bytes(self):
        return self.committed_bytes + self.reserved_bytes

    @property
    def available_bytes(self):
        return max(self.global_storage_cap_bytes - self.consumed_bytes, 0)

    @property
    def percent_consumed(self):
        if not self.global_storage_cap_bytes:
            return 100
        return round((self.consumed_bytes / self.global_storage_cap_bytes) * 100, 2)

    def __str__(self):
        return 'Video Storage & Processing'


class ListingVideo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='videos', null=True, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='listing_videos')
    object_key = models.CharField(max_length=500, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    file_size = models.PositiveBigIntegerField()
    upload_status = models.CharField(max_length=20, choices=ListingVideoStatus.choices, default=ListingVideoStatus.PENDING)
    upload_id = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    poster_object_key = models.CharField(max_length=500, blank=True)
    poster_url = models.URLField(blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    moderation_state = models.CharField(max_length=30, default='unreviewed')
    verification_metadata = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=255, blank=True)
    upload_expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    cleanup_required = models.BooleanField(default=False)
    object_deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['owner', 'upload_status']),
            models.Index(fields=['listing', 'upload_status']),
            models.Index(fields=['upload_expires_at']),
        ]

    def __str__(self):
        target = self.listing.title if self.listing_id else 'unattached listing'
        return f"Video for {target}"

    @property
    def is_ready(self):
        return self.upload_status == ListingVideoStatus.READY

    @property
    def is_expired_pending(self):
        return self.upload_status in {ListingVideoStatus.PENDING, ListingVideoStatus.UPLOADING} and timezone.now() > self.upload_expires_at


class VideoUploadReservation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='video_upload_reservations')
    tenant = models.CharField(max_length=120, blank=True)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='video_upload_reservations', null=True, blank=True)
    video = models.OneToOneField(ListingVideo, on_delete=models.SET_NULL, related_name='reservation', null=True, blank=True)
    object_key = models.CharField(max_length=500, unique=True)
    declared_size = models.PositiveBigIntegerField()
    expected_processed_size = models.PositiveBigIntegerField(default=0)
    reserved_temporary_bytes = models.PositiveBigIntegerField(default=0)
    reserved_final_bytes = models.PositiveBigIntegerField(default=0)
    actual_uploaded_size = models.PositiveBigIntegerField(null=True, blank=True)
    actual_processed_size = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=VideoReservationStatus.choices, default=VideoReservationStatus.RESERVED)
    expiration_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_time = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['expiration_time', 'status']),
        ]

    @property
    def active_reserved_bytes(self):
        if self.status in {
            VideoReservationStatus.RESERVED,
            VideoReservationStatus.UPLOADING,
            VideoReservationStatus.UPLOADED_TEMPORARILY,
            VideoReservationStatus.QUEUED,
            VideoReservationStatus.PROCESSING,
        }:
            return self.reserved_temporary_bytes + self.reserved_final_bytes
        return 0


class GlobalVideoStorageAudit(models.Model):
    policy = models.ForeignKey(GlobalVideoStoragePolicy, on_delete=models.CASCADE, related_name='audit_events')
    old_value = models.PositiveBigIntegerField(null=True, blank=True)
    new_value = models.PositiveBigIntegerField(null=True, blank=True)
    administrator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    reason = models.TextField(blank=True)
    event_type = models.CharField(max_length=40, default='cap_changed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class VehicleDetails(models.Model):
    listing = models.OneToOneField(Listing, on_delete=models.CASCADE, related_name='vehicle_details')
    category = models.CharField(max_length=30, choices=[('car','Car'),('motorcycle','Motorcycle'),('van','Van'),('truck','Truck'),('bus','Bus'),('other','Other')])
    trim = models.CharField(max_length=60, blank=True)
    condition = models.CharField(max_length=20, choices=[('new','New'),('foreign_used','Foreign used'),('locally_used','Locally used')])
    body_type = models.CharField(max_length=40, blank=True)
    exterior_colour = models.CharField(max_length=40, blank=True)
    fuel_type = models.CharField(max_length=20, blank=True)
    transmission = models.CharField(max_length=20, blank=True)
    engine_capacity_cc = models.PositiveIntegerField(null=True, blank=True)
    drivetrain = models.CharField(max_length=20, blank=True)
    steering_position = models.CharField(max_length=10, blank=True)
    doors = models.PositiveSmallIntegerField(null=True, blank=True)
    seats = models.PositiveSmallIntegerField(null=True, blank=True)
    registration_status = models.CharField(max_length=30, blank=True)
    service_history = models.BooleanField(default=False)
    accident_history = models.BooleanField(default=False)
    imported = models.BooleanField(default=False)
    warranty = models.BooleanField(default=False)
    financing = models.BooleanField(default=False)
    trade_in = models.BooleanField(default=False)
    delivery = models.BooleanField(default=False)
    features = models.CharField(max_length=500, blank=True)

    @property
    def features_list(self):
        return [value for value in self.features.split(',') if value]


class SMEDetails(models.Model):
    listing = models.OneToOneField(Listing, on_delete=models.CASCADE, related_name='sme_details')
    kind = models.CharField(max_length=10, choices=[('product','Product'),('service','Service')])
    subcategory = models.CharField(max_length=80, blank=True)
    brand = models.CharField(max_length=80, blank=True)
    condition = models.CharField(max_length=30, blank=True)
    price_type = models.CharField(max_length=20, choices=[('fixed','Fixed price'),('starting','Starting from'),('negotiable','Negotiable'),('contact','Contact for price')], default='fixed')
    stock_available = models.BooleanField(default=False)
    selling_unit = models.CharField(max_length=40, blank=True)
    minimum_order = models.PositiveIntegerField(null=True, blank=True)
    delivery = models.BooleanField(default=False)
    pickup = models.BooleanField(default=False)
    service_area = models.CharField(max_length=160, blank=True)
    customers_visit = models.BooleanField(default=False)
    provider_visits = models.BooleanField(default=False)
    appointment_required = models.BooleanField(default=False)
    availability = models.CharField(max_length=160, blank=True)
    completion_time = models.CharField(max_length=80, blank=True)
    emergency_service = models.BooleanField(default=False)
    materials_included = models.BooleanField(default=False)
    warranty = models.BooleanField(default=False)
    return_exchange = models.BooleanField(default=False)
    specifications = models.JSONField(default=dict, blank=True)


class SavedListing(models.Model):
    """User bookmarks / saved listings."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_listings',
    )
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='saved_by',
    )
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'listing')


class ListingReview(models.Model):
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listing_reviews',
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('listing', 'reviewer')

    def __str__(self):
        return f"{self.listing.title} review by {self.reviewer}"


class ListingView(models.Model):
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='unique_views',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listing_views',
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=40, blank=True)
    viewer_token = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('listing', 'viewer_token')

    def __str__(self):
        return f"View of {self.listing.title} by {self.viewer_token}"
