from django.shortcuts import render
from django.core.paginator import Paginator
from apps.listings.models import Listing, ListingStatus, ListingType, SavedListing


def home(request):
    listing_type = request.GET.get('type', 'rental')
    property_filter = request.GET.get('property', '')

    qs = Listing.objects.filter(status=ListingStatus.ACTIVE)

    if listing_type in ['rental', 'sme', 'auto']:
        qs = qs.filter(listing_type=listing_type)

    if property_filter:
        qs = qs.filter(property_type=property_filter)

    # Featured listings (horizontal scroll strip)
    featured = qs.filter(is_featured=True).select_related('owner')[:6]

    # Main grid
    paginator = Paginator(qs.filter(is_featured=False).select_related('owner').prefetch_related('images'), 12)
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
    })
