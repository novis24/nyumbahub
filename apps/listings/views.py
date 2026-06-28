from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.db.models import Avg, Count, F
from datetime import timedelta
from .models import (
    Listing,
    ListingImage,
    ListingReview,
    ListingStatus,
    ListingType,
    ListingView,
    SavedListing,
)
from .forms import ListingForm, ListingReviewForm

AMENITY_CHOICES = [
    'wifi', 'water', 'electricity', 'security', 'parking',
    'generator', 'borehole', 'cctv', 'gym', 'pool',
]


def _get_saved_ids_for_user(user):
    if not user.is_authenticated:
        return set()
    return set(
        SavedListing.objects.filter(user=user).values_list('listing_id', flat=True)
    )


def _owner_review_stats(owner):
    stats = ListingReview.objects.filter(listing__owner=owner).aggregate(
        average_rating=Avg('rating'),
        total_reviews=Count('id'),
    )
    return {
        'average_rating': stats['average_rating'] or 0,
        'total_reviews': stats['total_reviews'] or 0,
    }


def _track_listing_view(request, listing):
    if listing.owner == request.user or listing.status != ListingStatus.ACTIVE:
        return

    if request.user.is_authenticated:
        viewer_token = f"user:{request.user.pk}"
        defaults = {'user': request.user}
    else:
        if not request.session.session_key:
            request.session.save()
        viewer_token = f"session:{request.session.session_key}"
        defaults = {'session_key': request.session.session_key}

    view, created = ListingView.objects.get_or_create(
        listing=listing,
        viewer_token=viewer_token,
        defaults=defaults,
    )
    if created:
        Listing.objects.filter(pk=listing.pk).update(views_count=F('views_count') + 1)
        listing.refresh_from_db(fields=['views_count'])
    elif not view.session_key and request.session.session_key and not request.user.is_authenticated:
        view.session_key = request.session.session_key
        view.save(update_fields=['session_key'])


def listing_detail(request, slug):
    listing = get_object_or_404(
        Listing.objects.select_related('owner').prefetch_related('images', 'reviews__reviewer'),
        slug=slug,
    )
    if listing.status != ListingStatus.ACTIVE and listing.owner != request.user:
        raise Http404('Listing not found.')

    _track_listing_view(request, listing)

    images = listing.images.all()
    saved_ids = _get_saved_ids_for_user(request.user)
    is_saved = listing.id in saved_ids
    owner_review_stats = _owner_review_stats(listing.owner)
    user_review = None
    review_form = None
    can_review = request.user.is_authenticated and request.user != listing.owner
    if can_review:
        user_review = listing.reviews.filter(reviewer=request.user).first()
        review_form = ListingReviewForm(instance=user_review)

    return render(request, 'listings/detail.html', {
        'listing': listing,
        'images': images,
        'is_saved': is_saved,
        'saved_ids': saved_ids,
        'owner_review_stats': owner_review_stats,
        'review_form': review_form,
        'user_review': user_review,
        'can_review': can_review,
        'reviews': listing.reviews.all(),
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
        messages.error(request, 'Only provider accounts can post listings.')
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
            max_images = sub.max_images if sub else 20
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
            if listing.status == ListingStatus.ACTIVE:
                return redirect('listings:detail', slug=listing.slug)
            return redirect('listings:my_listings')
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
        lst.status = request.POST.get('status', listing.status)
        amenities = request.POST.getlist('amenities')
        lst.amenities = ','.join(amenities)
        lst.save()
        if request.POST.get('cover_image'):
            lst.images.update(is_cover=False)
            lst.images.filter(id=request.POST.get('cover_image')).update(is_cover=True)

        remove_ids = request.POST.getlist('remove_image_ids')
        if remove_ids:
            lst.images.filter(id__in=remove_ids).delete()

        existing_images = list(lst.images.all())
        max_images = request.user.active_subscription.max_images if request.user.active_subscription else 20
        slots_left = max(max_images - len(existing_images), 0)
        new_images = request.FILES.getlist('images')
        for offset, image in enumerate(new_images[:slots_left], start=len(existing_images)):
            ListingImage.objects.create(
                listing=lst,
                image=image,
                is_cover=False,
                order=offset,
            )

        final_images = list(lst.images.all())
        cover_id = request.POST.get('cover_image')
        if cover_id and any(str(image.id) == cover_id for image in final_images):
            lst.images.exclude(id=cover_id).update(is_cover=False)
            lst.images.filter(id=cover_id).update(is_cover=True)
        elif final_images and not any(image.is_cover for image in final_images):
            first_image = final_images[0]
            lst.images.exclude(id=first_image.id).update(is_cover=False)
            lst.images.filter(id=first_image.id).update(is_cover=True)

        for order, image in enumerate(lst.images.all()):
            if image.order != order:
                image.order = order
                image.save(update_fields=['order'])
        messages.success(request, 'Listing updated.')
        if lst.status == ListingStatus.ACTIVE:
            return redirect('listings:detail', slug=lst.slug)
        return redirect('listings:my_listings')

    return render(request, 'listings/edit.html', {
        'form': form,
        'listing': listing,
        'amenity_choices': AMENITY_CHOICES,
        'status_choices': ListingStatus.choices,
        'current_images': listing.images.all(),
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
        return JsonResponse({'saved': False, 'likes_count': listing.saved_by.count()})
    return JsonResponse({'saved': True, 'likes_count': listing.saved_by.count()})


@login_required
def saved_listings(request):
    saved = SavedListing.objects.filter(
        user=request.user
    ).select_related('listing').prefetch_related('listing__images').order_by('-saved_at')
    saved_ids = _get_saved_ids_for_user(request.user)
    return render(request, 'listings/saved.html', {'saved': saved, 'saved_ids': saved_ids})


@login_required
@require_POST
def submit_review(request, slug):
    listing = get_object_or_404(Listing, slug=slug, status=ListingStatus.ACTIVE)
    if listing.owner == request.user:
        messages.error(request, 'You cannot review your own listing.')
        return redirect('listings:detail', slug=listing.slug)

    instance = ListingReview.objects.filter(listing=listing, reviewer=request.user).first()
    form = ListingReviewForm(request.POST, instance=instance)
    if form.is_valid():
        review = form.save(commit=False)
        review.listing = listing
        review.reviewer = request.user
        review.save()
        messages.success(request, 'Your review has been saved.')
    else:
        messages.error(request, 'Please add a valid star rating before submitting your review.')

    return redirect('listings:detail', slug=listing.slug)
