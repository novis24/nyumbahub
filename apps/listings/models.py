from django.db import models
from django.conf import settings
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
