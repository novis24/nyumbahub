from django.shortcuts import render
from django.http import FileResponse
from django.conf import settings
from django.views.decorators.cache import cache_control
from django.core.paginator import Paginator
from django.db.models import Avg, Case, Count, IntegerField, When
from apps.listings.models import Listing, ListingStatus, ListingType, SavedListing


def home(request):
    listing_type = request.GET.get('type', 'rental')
    if listing_type not in ListingType.values:
        listing_type = ListingType.RENTAL
    property_filter = request.GET.get('property', '')

    qs = Listing.objects.filter(status=ListingStatus.ACTIVE)

    if listing_type in ['rental', 'sme', 'auto']:
        qs = qs.filter(listing_type=listing_type)

    if property_filter:
        qs = qs.filter(property_type=property_filter)

    # Featured listings (horizontal scroll strip)
    featured = qs.filter(is_featured=True).select_related('owner').prefetch_related('images', 'reviews')[:6]
    hero_listing = (
        qs.filter(images__isnull=False)
        .annotate(
            verified_rank=Case(
                When(owner__verification_status='verified', then=1),
                default=0,
                output_field=IntegerField(),
            ),
            rating_rank=Avg('reviews__rating'),
        )
        .select_related('owner')
        .prefetch_related('images')
        .order_by('-verified_rank', '-rating_rank', '-is_featured', '-created_at')
        .first()
    )

    hero_content = {
        ListingType.RENTAL: {
            'eyebrow': 'Trusted homes across Tanzania',
            'title_start': 'Find spaces that', 'title_emphasis': 'move',
            'title_end': 'your life forward.',
            'description': 'Explore rentals, estates, hostels and single rooms in neighbourhoods that fit your life.',
            'placeholder': 'e.g. 3 bedroom apartment',
        },
        ListingType.AUTO: {
            'eyebrow': 'Trusted vehicles across Tanzania',
            'title_start': 'Find the vehicle that', 'title_emphasis': 'moves',
            'title_end': 'you forward.',
            'description': 'Explore cars, vans, motorcycles and commercial vehicles from accountable sellers.',
            'placeholder': 'e.g. Toyota Harrier 2020',
        },
        ListingType.SME: {
            'eyebrow': 'Discover Tanzanian businesses',
            'title_start': 'Find local businesses that', 'title_emphasis': 'help',
            'title_end': 'you move forward.',
            'description': 'Explore products, services, shops and growing businesses near you.',
            'placeholder': 'e.g. furniture or catering',
        },
    }[listing_type]

    # Main grid
    paginator = Paginator(qs.filter(is_featured=False).select_related('owner').prefetch_related('images', 'reviews'), 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Saved listing IDs for the heart icon state
    saved_ids = set()
    if request.user.is_authenticated:
        saved_ids = set(
            SavedListing.objects.filter(user=request.user).values_list('listing_id', flat=True)
        )

    # If HTMX infinite scroll request — return only the grid items fragment
    if request.htmx and int(page_number) > 1:
        return render(request, 'partials/listing_grid_items.html', {
            'listings': page_obj,
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
            'saved_ids': saved_ids,
            'active_type': listing_type,
        })

    return render(request, 'core/home.html', {
        'listings': page_obj,
        'featured_listings': featured,
        'active_type': listing_type,
        'property_filter': property_filter,
        'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        'saved_ids': saved_ids,
        'hero_listing': hero_listing,
        'hero_content': hero_content,
        'popular_cities': Listing.objects.filter(status=ListingStatus.ACTIVE).values('city').annotate(total=Count('id')).order_by('-total')[:5],
    })


@cache_control(no_cache=True, must_revalidate=True)
def service_worker(request):
    response = FileResponse(
        open(settings.BASE_DIR / 'static' / 'sw.js', 'rb'),
        content_type='application/javascript',
    )
    response['Service-Worker-Allowed'] = '/'
    return response


def privacy(request):
    return render(request, 'core/privacy.html')


def terms(request):
    return render(request, 'core/terms.html')
