from django.shortcuts import render
from django.db.models import Q
from apps.listings.models import (
    Listing, ListingStatus, ListingType, PropertyType, SavedListing,
    SMEDetails, VehicleDetails,
)


def search_results(request):
    q = request.GET.get('q', '').strip()
    listing_type = request.GET.get('type', '')
    city = request.GET.get('city', '').strip()
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    property_type = request.GET.get('property', '')
    furnished = request.GET.get('furnished', '')
    students = request.GET.get('students', '')
    vehicle_make = request.GET.get('vehicle_make', '').strip()
    vehicle_model = request.GET.get('vehicle_model', '').strip()
    min_year = request.GET.get('min_year', '')
    max_year = request.GET.get('max_year', '')
    vehicle_condition = request.GET.get('vehicle_condition', '')
    vehicle_category = request.GET.get('vehicle_category', '')
    sme_kind = request.GET.get('sme_kind', '')
    business_category = request.GET.get('business_category', '').strip()
    price_type = request.GET.get('price_type', '')

    qs = Listing.objects.filter(status=ListingStatus.ACTIVE).select_related('owner').prefetch_related('images', 'videos', 'reviews')

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(description__icontains=q) |
            Q(location__icontains=q) |
            Q(city__icontains=q) |
            Q(vehicle_make__icontains=q) |
            Q(vehicle_model__icontains=q) |
            Q(business_category__icontains=q)
        )
    if listing_type in ListingType.values:
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
    if listing_type == ListingType.AUTO:
        if vehicle_make:
            qs = qs.filter(vehicle_make__icontains=vehicle_make)
        if vehicle_model:
            qs = qs.filter(vehicle_model__icontains=vehicle_model)
        if vehicle_condition:
            qs = qs.filter(vehicle_details__condition=vehicle_condition)
        if vehicle_category:
            qs = qs.filter(vehicle_details__category=vehicle_category)
        try:
            if min_year:
                qs = qs.filter(vehicle_year__gte=int(min_year))
            if max_year:
                qs = qs.filter(vehicle_year__lte=int(max_year))
        except ValueError:
            pass
    if listing_type == ListingType.SME:
        if sme_kind:
            qs = qs.filter(sme_details__kind=sme_kind)
        if business_category:
            qs = qs.filter(business_category__icontains=business_category)
        if price_type:
            qs = qs.filter(sme_details__price_type=price_type)

    count = qs.count()
    saved_ids = set()
    if request.user.is_authenticated:
        saved_ids = set(
            SavedListing.objects.filter(user=request.user).values_list('listing_id', flat=True)
        )

    # HTMX partial — just the grid
    if request.htmx and request.GET.get('partial'):
        return render(request, 'partials/search_results_grid.html', {
            'listings': qs[:24],
            'count': count,
            'saved_ids': saved_ids,
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
        'vehicle_make': vehicle_make,
        'vehicle_model': vehicle_model,
        'min_year': min_year,
        'max_year': max_year,
        'vehicle_condition': vehicle_condition,
        'vehicle_category': vehicle_category,
        'vehicle_condition_choices': VehicleDetails._meta.get_field('condition').choices,
        'vehicle_category_choices': VehicleDetails._meta.get_field('category').choices,
        'sme_kind': sme_kind,
        'business_category': business_category,
        'price_type': price_type,
        'sme_kind_choices': SMEDetails._meta.get_field('kind').choices,
        'price_type_choices': SMEDetails._meta.get_field('price_type').choices,
        'saved_ids': saved_ids,
    })
