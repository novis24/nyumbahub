import json
import logging
import uuid

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_GET, require_POST
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.conf import settings
from django.db import transaction
from django.db.models import Avg, Count, F, FloatField, Q
from django.db.models.functions import ACos, Cos, Radians, Sin
from datetime import timedelta
from .models import (
    Listing,
    ListingImage,
    ListingReview,
    ListingStatus,
    ListingType,
    ListingVideo,
    ListingVideoStatus,
    ListingView,
    SavedListing,
    Cart,
    CartItem,
    ProductCategory,
    SMEOrder,
    SMEOrderItem,
)
from .forms import ListingForm, ListingReviewForm
from .services.r2_storage import (
    create_presigned_playback_url,
    create_presigned_upload,
    delete_object,
    make_video_object_key,
    verify_uploaded_object,
)
from .services.video_policy import get_video_upload_policy, validate_video_upload_request
from .services.video_quota import (
    complete_reservation,
    release_committed_video,
    release_reservation,
    reserve_video_capacity,
    mark_uploaded_temporarily,
)
from .services.image_policy import validate_listing_images
from .models import VideoReservationStatus

logger = logging.getLogger(__name__)

AMENITY_CHOICES = [
    'wifi', 'water', 'electricity', 'security', 'parking',
    'generator', 'borehole', 'cctv', 'gym', 'pool',
]

ROLE_LISTING_TYPES = {'landlord': ListingType.RENTAL, 'sme': ListingType.SME, 'auto': ListingType.AUTO}


class ListingImageStorageError(Exception):
    pass


def active_public_listings():
    return Listing.objects.filter(status=ListingStatus.ACTIVE, owner__is_active=True).select_related('owner').prefetch_related('images', 'videos', 'reviews')


def with_distance(qs, lat, lng):
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return qs
    return qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True).annotate(
        distance_km=6371 * ACos(
            Cos(Radians(lat)) * Cos(Radians('latitude')) * Cos(Radians('longitude') - Radians(lng)) +
            Sin(Radians(lat)) * Sin(Radians('latitude')),
            output_field=FloatField(),
        )
    )


def provider_cards(qs, limit=12, order='recent'):
    if order == 'nearby':
        ordered = qs.order_by('distance_km', '-is_featured', '-created_at')
    else:
        ordered = qs.order_by('-views_count' if order == 'popular' else '-created_at')
    seen = set()
    cards = []
    for prefer_images in (True, False):
        for listing in ordered:
            if listing.owner_id in seen:
                continue
            if prefer_images and not listing.cover_image:
                continue
            seen.add(listing.owner_id)
            cards.append(listing)
            if len(cards) >= limit:
                return cards
    return cards


def cart_for_request(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        if request.session.session_key:
            guest = Cart.objects.filter(user__isnull=True, session_key=request.session.session_key).first()
            if guest:
                for item in guest.items.select_related('listing'):
                    target, created = CartItem.objects.get_or_create(cart=cart, listing=item.listing, defaults={'quantity': item.quantity})
                    if not created:
                        target.quantity += item.quantity
                        target.save(update_fields=['quantity', 'updated_at'])
                guest.delete()
        return cart
    if not request.session.session_key:
        request.session.save()
    cart, _ = Cart.objects.get_or_create(user__isnull=True, session_key=request.session.session_key)
    return cart


def cart_payload(cart):
    items = []
    total = 0
    for item in cart.items.select_related('listing', 'listing__owner').prefetch_related('listing__images'):
        listing = item.listing
        if listing.listing_type != ListingType.SME or listing.status != ListingStatus.ACTIVE or not listing.owner.is_active:
            continue
        line_total = int(item.line_total)
        total += line_total
        items.append({
            'id': item.id,
            'listing_id': str(listing.id),
            'title': listing.title,
            'quantity': item.quantity,
            'unit_price': int(listing.price),
            'line_total': line_total,
            'url': listing.get_absolute_url(),
            'image': listing.cover_image.image.url if listing.cover_image else '',
        })
    return {'count': sum(item['quantity'] for item in items), 'total': total, 'items': items}


def _get_saved_ids_for_user(user):
    if not user.is_authenticated:
        return set()
    return set(
        SavedListing.objects.filter(user=user).values_list('listing_id', flat=True)
    )


def _product_attributes_from_post(request):
    attrs = {}
    for key, value in request.POST.items():
        if key.startswith('attr_') and value.strip():
            attrs[key[5:]] = value.strip()
    return attrs


def _uploaded_file_metadata(uploaded_file):
    return {
        'filename': getattr(uploaded_file, 'name', ''),
        'content_type': getattr(uploaded_file, 'content_type', ''),
        'size': getattr(uploaded_file, 'size', None),
    }


def _delete_uploaded_listing_images(storage_names):
    for storage_name in storage_names:
        try:
            ListingImage._meta.get_field('image').storage.delete(storage_name)
        except Exception:
            logger.exception('listing_image_cleanup_failed', extra={'storage_name': storage_name})


def _add_image_validation_error(form, exc):
    messages = getattr(exc, 'messages', None) or [str(exc)]
    form.add_error(None, messages[0])


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
        Listing.objects.select_related('owner').prefetch_related('images', 'videos', 'reviews__reviewer'),
        slug=slug,
    )
    if listing.status != ListingStatus.ACTIVE and listing.owner != request.user:
        raise Http404(_('Listing not found.'))

    _track_listing_view(request, listing)

    images = listing.images.all()
    videos = listing.videos.filter(upload_status=ListingVideoStatus.READY)
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
        'videos': videos,
        'is_saved': is_saved,
        'saved_ids': saved_ids,
        'owner_review_stats': owner_review_stats,
        'review_form': review_form,
        'user_review': user_review,
        'can_review': can_review,
        'reviews': listing.reviews.all(),
        'geoapify_key': settings.GEOAPIFY_BROWSER_KEY,
        'show_sme_cart': listing.listing_type == ListingType.SME,
    })


def provider_gallery(request, owner_id):
    provider_listing_qs = active_public_listings().filter(owner_id=owner_id)
    representative = provider_listing_qs.order_by('-is_featured', '-created_at').first()
    if not representative:
        raise Http404(_('Provider not found.'))
    category = request.GET.get('category', '')
    available_categories = list(provider_listing_qs.values_list('listing_type', flat=True).distinct())
    if category not in available_categories:
        category = available_categories[0] if len(available_categories) == 1 else ''
    listings = provider_listing_qs
    if category:
        listings = listings.filter(listing_type=category)
    saved_ids = _get_saved_ids_for_user(request.user)
    return render(request, 'listings/provider_gallery.html', {
        'provider': representative.owner,
        'representative': representative,
        'listings': listings.order_by('-is_featured', '-created_at'),
        'available_categories': available_categories,
        'active_category': category,
        'saved_ids': saved_ids,
        'show_sme_cart': category == ListingType.SME or (len(available_categories) == 1 and available_categories[0] == ListingType.SME),
    })


@require_GET
def cart_state(request):
    return JsonResponse(cart_payload(cart_for_request(request)))


@require_POST
def add_to_cart(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id, status=ListingStatus.ACTIVE, owner__is_active=True)
    if listing.listing_type != ListingType.SME:
        return JsonResponse({'error': _('Only SME products can be added to cart.')}, status=400)
    details = getattr(listing, 'sme_details', None)
    if details and not details.stock_available and details.kind == 'product':
        return JsonResponse({'error': _('This product is currently unavailable.')}, status=400)
    cart = cart_for_request(request)
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    quantity = max(int(payload.get('quantity', 1)), 1)
    item, created = CartItem.objects.get_or_create(cart=cart, listing=listing, defaults={'quantity': quantity})
    if not created:
        item.quantity += quantity
        item.save(update_fields=['quantity', 'updated_at'])
    return JsonResponse(cart_payload(cart))


@require_POST
def update_cart_item(request, item_id):
    cart = cart_for_request(request)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    try:
        payload = json.loads(request.body.decode('utf-8'))
        quantity = int(payload.get('quantity', 1))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return JsonResponse({'error': _('Invalid quantity.')}, status=400)
    if item.listing.listing_type != ListingType.SME:
        item.delete()
        return JsonResponse(cart_payload(cart), status=400)
    if quantity <= 0:
        item.delete()
    else:
        item.quantity = quantity
        item.save(update_fields=['quantity', 'updated_at'])
    return JsonResponse(cart_payload(cart))


@require_POST
def clear_cart(request):
    cart = cart_for_request(request)
    cart.items.all().delete()
    return JsonResponse(cart_payload(cart))


def cart_page(request):
    cart = cart_for_request(request)
    return render(request, 'listings/cart.html', {'cart_state': cart_payload(cart), 'show_sme_cart': True})


def checkout(request):
    cart = cart_for_request(request)
    payload = cart_payload(cart)
    if not payload['items']:
        messages.error(request, _('Your SME cart is empty.'))
        return redirect('listings:cart')
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        if not customer_name or not customer_phone:
            messages.error(request, _('Add your name and phone number to request the order.'))
            return render(request, 'listings/checkout.html', {'cart_state': payload, 'show_sme_cart': True})
        with transaction.atomic():
            cart = Cart.objects.select_for_update().get(pk=cart.pk)
            payload = cart_payload(cart)
            if not payload['items']:
                messages.error(request, _('Your SME cart is empty.'))
                return redirect('listings:cart')
            order = SMEOrder.objects.create(
                buyer=request.user if request.user.is_authenticated else None,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_email=request.POST.get('customer_email', '').strip(),
                fulfillment_method=request.POST.get('fulfillment_method', 'delivery'),
                delivery_location=request.POST.get('delivery_location', '').strip(),
                notes=request.POST.get('notes', '').strip(),
                total=payload['total'],
            )
            for row in payload['items']:
                listing = Listing.objects.select_for_update().get(id=row['listing_id'], status=ListingStatus.ACTIVE, listing_type=ListingType.SME)
                SMEOrderItem.objects.create(
                    order=order,
                    seller=listing.owner,
                    listing=listing,
                    title=listing.title,
                    unit_price=listing.price,
                    quantity=row['quantity'],
                    line_total=listing.price * row['quantity'],
                )
            cart.items.all().delete()
        return redirect('listings:order_detail', order_id=order.id, access_key=order.access_key)
    return render(request, 'listings/checkout.html', {'cart_state': payload, 'show_sme_cart': True})


def order_detail(request, order_id, access_key):
    order = get_object_or_404(SMEOrder.objects.prefetch_related('items__listing'), id=order_id)
    has_private_link = order.access_key == access_key
    if not has_private_link and not (
        request.user.is_authenticated
        and (order.buyer_id == request.user.id or order.items.filter(seller=request.user).exists() or request.user.is_staff)
    ):
        raise Http404(_('Order not found.'))
    visible_items = order.items.all()
    if request.user.is_authenticated and order.buyer_id != request.user.id and not request.user.is_staff:
        visible_items = visible_items.filter(seller=request.user)
    return render(request, 'listings/order_detail.html', {'order': order, 'visible_items': visible_items, 'show_sme_cart': True})


@login_required
def my_listings(request):
    listings = request.user.listings.select_related('owner').prefetch_related('images', 'videos').order_by('-created_at')
    sub = request.user.active_subscription
    return render(request, 'listings/my_listings.html', {
        'listings': listings,
        'subscription': sub,
    })


@login_required
def create_listing(request):
    if not request.user.is_provider:
        messages.error(request, _('Only provider accounts can post listings.'))
        return redirect('core:home')

    # Role determines default listing type
    default_type = ROLE_LISTING_TYPES.get(request.user.role)
    if not default_type:
        messages.error(request, _('Your account cannot create listings.'))
        return redirect('core:home')

    if request.method == 'POST':
        form = ListingForm(request.POST, request.FILES, listing_type=default_type)
        submitted_token = request.POST.get('create_token', '')
        session_token = request.session.get('listing_create_token', '')
        if not submitted_token or submitted_token != session_token:
            form.add_error(None, _('This listing submission has already been processed. Please review your listings before trying again.'))
        if form.is_valid():
            images = request.FILES.getlist('images')
            sub = request.user.active_subscription
            max_images = sub.max_images if sub else 20
            if len(images) > max_images:
                form.add_error(None, _('Your plan allows up to %(count)s photos per listing.') % {'count': max_images})
            else:
                try:
                    validate_listing_images(images)
                except ValidationError as exc:
                    first_image = images[0] if images else None
                    logger.info(
                        'listing_image_validation_failed',
                        extra={
                            'user_id': request.user.id,
                            'image': _uploaded_file_metadata(first_image) if first_image else {},
                            'exception_class': exc.__class__.__name__,
                        },
                    )
                    _add_image_validation_error(form, exc)

        if form.is_valid():
            uploaded_storage_names = []
            try:
                with transaction.atomic():
                    request.session.pop('listing_create_token', None)
                    request.session.modified = True
                    listing = form.save(commit=False)
                    listing.owner = request.user
                    listing.listing_type = default_type
                    requested_status = request.POST.get('status', ListingStatus.DRAFT)
                    listing.status = requested_status if requested_status in ListingStatus.values else ListingStatus.DRAFT
                    listing.amenities = ','.join(request.POST.getlist('amenities'))
                    if default_type == ListingType.SME:
                        listing.product_attributes = _product_attributes_from_post(request)

                    sub = request.user.active_subscription
                    if sub:
                        listing.expires_at = timezone.now() + timedelta(days=30)

                    listing.save()
                    form.save_details(listing)

                    pending_video_ids = request.POST.getlist('pending_video_ids')
                    pending_videos = ListingVideo.objects.select_for_update().filter(
                        id__in=pending_video_ids,
                        owner=request.user,
                        listing__isnull=True,
                        upload_status=ListingVideoStatus.READY,
                    )
                    for order, video in enumerate(pending_videos):
                        video.listing = listing
                        video.order = order
                        video.save(update_fields=['listing', 'order', 'updated_at'])

                    try:
                        for i, img in enumerate(images):
                            listing_image = ListingImage.objects.create(
                                listing=listing,
                                image=img,
                                is_cover=(i == 0),
                                order=i,
                            )
                            uploaded_storage_names.append(listing_image.image.name)
                    except Exception as exc:
                        logger.exception(
                            'listing_image_storage_failed',
                            extra={
                                'user_id': request.user.id,
                                'image': _uploaded_file_metadata(img),
                                'exception_class': exc.__class__.__name__,
                            },
                        )
                        _delete_uploaded_listing_images(uploaded_storage_names)
                        form.add_error(None, _('We could not upload one of your photos. Please try again with JPEG, PNG, or WebP images.'))
                        raise ListingImageStorageError from exc

                    if listing.status == ListingStatus.ACTIVE:
                        from apps.notifications.services import notify_marketplace_subscribers
                        transaction.on_commit(lambda listing=listing, request=request: notify_marketplace_subscribers(listing, request))
            except ListingImageStorageError:
                request.session['listing_create_token'] = submitted_token or uuid.uuid4().hex
                listing = None
            else:
                messages.success(
                    request,
                    _('Listing published!') if listing.status == 'active' else _('Draft saved.')
                )
                if listing.status == ListingStatus.ACTIVE:
                    return redirect('listings:detail', slug=listing.slug)
                return redirect('listings:my_listings')
    else:
        request.session['listing_create_token'] = uuid.uuid4().hex
        form = ListingForm(listing_type=default_type)

    return render(request, 'listings/create.html', {
        'form': form,
        'listing_type': default_type,
        'amenity_choices': AMENITY_CHOICES,
        'video_policy': get_video_upload_policy(request.user).as_dict(),
        'geoapify_key': settings.GEOAPIFY_BROWSER_KEY,
        'product_categories': ProductCategory.objects.filter(parent__isnull=True, is_active=True).prefetch_related('subcategories', 'attributes'),
        'create_token': request.session.get('listing_create_token', ''),
    })


@login_required
def edit_listing(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    was_active = listing.status == ListingStatus.ACTIVE
    form = ListingForm(request.POST or None, request.FILES or None, instance=listing, listing_type=listing.listing_type)

    if request.method == 'POST' and form.is_valid():
        lst = form.save(commit=False)
        lst.status = request.POST.get('status', listing.status)
        amenities = request.POST.getlist('amenities')
        lst.amenities = ','.join(amenities)
        if lst.listing_type == ListingType.SME:
            lst.product_attributes = _product_attributes_from_post(request)
        lst.save()
        form.save_details(lst)
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

        remove_video_ids = request.POST.getlist('remove_video_ids')
        if remove_video_ids:
            for video in lst.videos.filter(id__in=remove_video_ids, owner=request.user):
                _mark_video_deleted(video)

        for order, video_id in enumerate(request.POST.getlist('video_order')):
            lst.videos.filter(id=video_id, owner=request.user).update(order=order)

        messages.success(request, _('Listing updated.'))
        if lst.status == ListingStatus.ACTIVE:
            if not was_active:
                from apps.notifications.services import notify_marketplace_subscribers
                notify_marketplace_subscribers(lst, request)
            return redirect('listings:detail', slug=lst.slug)
        return redirect('listings:my_listings')

    return render(request, 'listings/edit.html', {
        'form': form,
        'listing': listing,
        'amenity_choices': AMENITY_CHOICES,
        'status_choices': ListingStatus.choices,
        'current_images': listing.images.all(),
        'current_videos': listing.videos.all(),
        'video_policy': get_video_upload_policy(request.user, listing).as_dict(),
        'listing_type': listing.listing_type,
        'geoapify_key': settings.GEOAPIFY_BROWSER_KEY,
        'product_categories': ProductCategory.objects.filter(parent__isnull=True, is_active=True).prefetch_related('subcategories', 'attributes'),
    })


@login_required
@require_POST
def delete_listing(request, slug):
    listing = get_object_or_404(Listing, slug=slug, owner=request.user)
    for video in listing.videos.exclude(upload_status=ListingVideoStatus.DELETED):
        if not _mark_video_deleted(video):
            messages.error(request, _('A listing video could not be removed from storage. Please try deleting again.'))
            return redirect('listings:edit', slug=listing.slug)
    listing.delete()
    messages.success(request, _('Listing deleted.'))
    return redirect('listings:my_listings')


@login_required
@require_POST
def create_video_upload(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': _('Invalid upload request.')}, status=400)

    listing = None
    listing_id = payload.get('listing_id')
    if listing_id:
        listing = get_object_or_404(Listing, id=listing_id, owner=request.user)

    filename = payload.get('filename', '')
    content_type = payload.get('content_type', '')
    declared_size = payload.get('file_size')
    optimize = bool(payload.get('optimize'))
    with transaction.atomic():
        policy, error = validate_video_upload_request(request.user, listing, filename, content_type, declared_size)
        if error:
            return JsonResponse({'error': error, 'policy': policy.as_dict()}, status=400)
        object_key = make_video_object_key(request.user.id, listing.id if listing else None, filename)
        video = ListingVideo.objects.create(
            listing=listing,
            owner=request.user,
            object_key=object_key,
            original_filename=filename[:255],
            content_type=content_type,
            file_size=int(declared_size),
            upload_status=ListingVideoStatus.PENDING,
            upload_expires_at=timezone.now() + timedelta(minutes=settings.R2_VIDEO_UPLOAD_SESSION_TTL_MINUTES),
            order=(listing.videos.count() if listing else request.user.listing_videos.filter(listing__isnull=True).count()),
        )
        reservation, error = reserve_video_capacity(
            user=request.user,
            listing=listing,
            video=video,
            declared_size=int(declared_size),
            optimize=optimize and policy.optimization_enabled,
        )
        if error:
            video.upload_status = ListingVideoStatus.FAILED
            video.error_message = error
            video.save(update_fields=['upload_status', 'error_message', 'updated_at'])
            return JsonResponse({'error': error, 'policy': policy.as_dict()}, status=503)

    try:
        upload = create_presigned_upload(video)
    except RuntimeError as exc:
        video.upload_status = ListingVideoStatus.FAILED
        video.error_message = str(exc)
        video.save(update_fields=['upload_status', 'error_message', 'updated_at'])
        release_reservation(reservation, VideoReservationStatus.FAILED, str(exc))
        return JsonResponse({'error': str(exc)}, status=503)

    video.upload_status = ListingVideoStatus.UPLOADING
    video.save(update_fields=['upload_status', 'updated_at'])
    return JsonResponse({'video_id': str(video.id), 'upload': upload, 'policy': policy.as_dict()})


@login_required
@require_POST
def complete_video_upload(request, video_id):
    video = get_object_or_404(ListingVideo, id=video_id, owner=request.user)
    if video.upload_status == ListingVideoStatus.READY:
        return JsonResponse({'video_id': str(video.id), 'status': video.upload_status})
    reservation = getattr(video, 'reservation', None)
    if video.is_expired_pending:
        video.upload_status = ListingVideoStatus.FAILED
        video.error_message = _('Upload session expired.')
        video.save(update_fields=['upload_status', 'error_message', 'updated_at'])
        if reservation:
            release_reservation(reservation, VideoReservationStatus.EXPIRED, video.error_message)
        return JsonResponse({'error': video.error_message}, status=400)
    ok, metadata = verify_uploaded_object(video)
    if not ok:
        video.upload_status = ListingVideoStatus.FAILED
        video.error_message = _('Uploaded object could not be verified.')
        video.verification_metadata = metadata
        video.save(update_fields=['upload_status', 'error_message', 'verification_metadata', 'updated_at'])
        if reservation:
            release_reservation(reservation, VideoReservationStatus.REJECTED, video.error_message)
        delete_object(video)
        return JsonResponse({'error': video.error_message}, status=400)
    actual_size = int(metadata.get('content_length') or video.file_size)
    if reservation:
        mark_uploaded_temporarily(reservation, actual_size)
        complete_reservation(reservation, actual_size)
    video.upload_status = ListingVideoStatus.READY
    video.completed_at = timezone.now()
    video.file_size = actual_size
    video.verification_metadata = metadata
    video.save(update_fields=['upload_status', 'completed_at', 'file_size', 'verification_metadata', 'updated_at'])
    return JsonResponse({'video_id': str(video.id), 'status': video.upload_status})


def video_playback_url(request, video_id):
    video = get_object_or_404(ListingVideo.objects.select_related('listing'), id=video_id, upload_status=ListingVideoStatus.READY)
    if video.listing and video.listing.status == ListingStatus.ACTIVE:
        pass
    elif not request.user.is_authenticated or (video.owner != request.user and not request.user.is_staff):
        raise Http404(_('Video not found.'))
    return JsonResponse({'url': create_presigned_playback_url(video), 'expires_in': settings.R2_SIGNED_URL_EXPIRY_SECONDS})


@login_required
@require_POST
def delete_video(request, video_id):
    video = get_object_or_404(ListingVideo, id=video_id, owner=request.user)
    _mark_video_deleted(video)
    return JsonResponse({'deleted': True})


def _mark_video_deleted(video):
    deleted = delete_object(video)
    was_committed = video.upload_status == ListingVideoStatus.READY
    reservation = getattr(video, 'reservation', None)
    video.upload_status = ListingVideoStatus.DELETED
    video.cleanup_required = not deleted
    video.object_deleted_at = timezone.now() if deleted else None
    video.save(update_fields=['upload_status', 'cleanup_required', 'object_deleted_at', 'updated_at'])
    if was_committed:
        release_committed_video(video)
    elif reservation:
        release_reservation(reservation, VideoReservationStatus.DELETED, _('Video deleted before completion.'))
    return deleted


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
    ).select_related('listing', 'listing__owner').prefetch_related('listing__images').order_by('-saved_at')
    saved_ids = _get_saved_ids_for_user(request.user)
    return render(request, 'listings/saved.html', {'saved': saved, 'saved_ids': saved_ids})


@login_required
@require_POST
def submit_review(request, slug):
    listing = get_object_or_404(Listing, slug=slug, status=ListingStatus.ACTIVE)
    if listing.owner == request.user:
        messages.error(request, _('You cannot review your own listing.'))
        return redirect('listings:detail', slug=listing.slug)

    instance = ListingReview.objects.filter(listing=listing, reviewer=request.user).first()
    form = ListingReviewForm(request.POST, instance=instance)
    if form.is_valid():
        review = form.save(commit=False)
        review.listing = listing
        review.reviewer = request.user
        review.save()
        messages.success(request, _('Your review has been saved.'))
    else:
        messages.error(request, _('Please add a valid star rating before submitting your review.'))

    return redirect('listings:detail', slug=listing.slug)
