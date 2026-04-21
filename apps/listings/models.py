from django.db import models
from django.conf import settings
from django.utils.text import slugify
import uuid


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
