from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from .models import Listing, ListingImage, ListingStatus, ListingType, SavedListing
from .forms import ListingForm

AMENITY_CHOICES = [
    'wifi', 'water', 'electricity', 'security', 'parking',
    'generator', 'borehole', 'cctv', 'gym', 'pool',
]


def listing_detail(request, slug):
    listing = get_object_or_404(Listing, slug=slug, status=ListingStatus.ACTIVE)
    listing.views_count += 1
    listing.save(update_fields=['views_count'])

    images = listing.images.all()
    is_saved = False
    if request.user.is_authenticated:
        is_saved = SavedListing.objects.filter(user=request.user, listing=listing).exists()

    return render(request, 'listings/detail.html', {
        'listing': listing,
        'images': images,
        'is_saved': is_saved,
    })


@login_required
def my_listings(request):
    listings = request.user.listings.prefetch_related('images').order_by('-created_at')
    sub = request.user.active_subscription
    return render(request, 'listings/my_listings.html', {
        'listings': listings,
        'subscription': sub,
    })


@login_required
def create_listing(request):
    if not request.user.is_provider:
        messages.error(request, 'Only landlords and SME accounts can post listings.')
        return redirect('core:home')

    # Role determines default listing type
    default_type = {
        'landlord': 'rental',
        'sme': 'sme',
        'auto': 'auto',
    }.get(request.user.role, 'rental')

    if request.method == 'POST':
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.listing_type = request.POST.get('listing_type', default_type)
            listing.status = request.POST.get('status', ListingStatus.DRAFT)

            # Amenities — collect from checkboxes
            amenities = request.POST.getlist('amenities')
            listing.amenities = ','.join(amenities)

            # Set expiry based on subscription
            sub = request.user.active_subscription
            if sub:
                listing.expires_at = timezone.now() + timedelta(days=30)

            listing.save()

            # Handle images
            images = request.FILES.getlist('images')
            sub = request.user.active_subscription
            max_images = sub.max_images if sub else 3
            for i, img in enumerate(images[:max_images]):
                ListingImage.objects.create(
                    listing=listing,
                    image=img,
                    is_cover=(i == 0),
                    order=i,
                )

            messages.success(
                request,
                'Listing published!' if listing.status == 'active' else 'Draft saved.'
            )
            return redirect('listings:detail', slug=listing.slug)
    else:
        form = ListingForm(initial={'listing_type': default_type})

    return render(request, 'listings/create.html', {
        'form': form,
        'listing_type': default_type,
        'amenity_choices': AMENITY_CHOICES,
        'type_choices': [('rental', 'Rental'), ('sme', 'SME'), ('auto', 'Auto')],
    })


@login_required
def edit_listing(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    form = ListingForm(request.POST or None, request.FILES or None, instance=listing)

    if request.method == 'POST' and form.is_valid():
        lst = form.save(commit=False)
        amenities = request.POST.getlist('amenities')
        lst.amenities = ','.join(amenities)
        lst.save()
        messages.success(request, 'Listing updated.')
        return redirect('listings:detail', slug=lst.slug)

    return render(request, 'listings/edit.html', {
        'form': form,
        'listing': listing,
        'amenity_choices': AMENITY_CHOICES,
    })


@login_required
@require_POST
def delete_listing(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    listing.delete()
    messages.success(request, 'Listing deleted.')
    return redirect('listings:my_listings')


@login_required
@require_POST
def toggle_save(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id)
    saved, created = SavedListing.objects.get_or_create(
        user=request.user, listing=listing
    )
    if not created:
        saved.delete()
        return JsonResponse({'saved': False})
    return JsonResponse({'saved': True})


@login_required
def saved_listings(request):
    saved = SavedListing.objects.filter(
        user=request.user
    ).select_related('listing').prefetch_related('listing__images').order_by('-saved_at')
    return render(request, 'listings/saved.html', {'saved': saved})
