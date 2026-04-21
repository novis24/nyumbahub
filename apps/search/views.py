from django.shortcuts import render
from django.db.models import Q
from apps.listings.models import Listing, ListingStatus, ListingType, PropertyType


def search_results(request):
    q = request.GET.get('q', '').strip()
    listing_type = request.GET.get('type', '')
    city = request.GET.get('city', '').strip()
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    property_type = request.GET.get('property', '')
    furnished = request.GET.get('furnished', '')
    students = request.GET.get('students', '')

    qs = Listing.objects.filter(status=ListingStatus.ACTIVE).select_related('owner').prefetch_related('images')

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(location__icontains=q) |
            Q(city__icontains=q)
        )
    if listing_type:
        qs = qs.filter(listing_type=listing_type)
    if city:
        qs = qs.filter(city__icontains=city)
    if min_price:
        try:
            qs = qs.filter(price__gte=int(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            qs = qs.filter(price__lte=int(max_price))
        except ValueError:
            pass
    if property_type:
        qs = qs.filter(property_type=property_type)
    if furnished == '1':
        qs = qs.filter(is_furnished=True)
    if students == '1':
        qs = qs.filter(allows_students=True)

    count = qs.count()

    # HTMX partial — just the grid
    if request.htmx and request.GET.get('partial'):
        return render(request, 'partials/search_results_grid.html', {
            'listings': qs[:24],
            'count': count,
        })

    return render(request, 'search/results.html', {
        'listings': qs[:24],
        'count': count,
        'q': q,
        'listing_type': listing_type,
        'city': city,
        'min_price': min_price,
        'max_price': max_price,
        'property_type': property_type,
        'property_choices': PropertyType.choices,
        'furnished': furnished,
        'students': students,
    })
