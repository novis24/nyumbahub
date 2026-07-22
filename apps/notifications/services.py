import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Max, Q
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from apps.accounts.models import CustomUser
from apps.listings.models import ListingType, ListingView
from .models import Notification, NotificationType

logger = logging.getLogger(__name__)


def _preferred_listing_types(user_ids):
    """Return each user's most-viewed category; ties prefer the latest activity."""
    rows = (
        ListingView.objects.filter(user_id__in=user_ids)
        .values('user_id', 'listing__listing_type')
        .annotate(total=Count('id'), latest=Max('created_at'))
        .order_by('user_id', '-total', '-latest')
    )
    preferences = {}
    for row in rows:
        preferences.setdefault(row['user_id'], row['listing__listing_type'])
    return preferences


def _send_push(user, listing, title, body):
    if not user.receives_push_notifications or not settings.FIREBASE_SERVICE_ACCOUNT_PATH:
        return
    tokens = list(user.push_devices.filter(is_active=True).values_list('token', flat=True))
    for token in tokens:
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging
            if not firebase_admin._apps:
                firebase_admin.initialize_app(
                    credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
                )
            messaging.send(messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body),
                webpush=messaging.WebpushConfig(
                    fcm_options=messaging.WebpushFCMOptions(link=listing.get_absolute_url())
                ),
                data={'url': listing.get_absolute_url(), 'listing_id': str(listing.pk)},
            ))
        except Exception:
            logger.exception('Firebase push delivery failed for user %s.', user.pk)


def notify_marketplace_subscribers(listing, request=None):
    """Email and notify opted-in users whose browsing preference matches a new listing."""
    subscribers = list(
        CustomUser.objects.filter(
            Q(receives_notifications=True) | Q(receives_push_notifications=True), is_active=True
        )
        .exclude(pk=listing.owner_id)
        .prefetch_related('push_devices')
    )
    preferences = _preferred_listing_types([user.pk for user in subscribers])
    type_label = dict(ListingType.choices).get(listing.listing_type, _('Marketplace'))
    title = _('New %(type)s listing') % {'type': str(type_label).lower()}
    body = _('%(title)s in %(location)s - %(price)s') % {
        'title': listing.title,
        'location': listing.location,
        'price': listing.price_per_month,
    }
    protocol = 'https' if request and request.is_secure() else 'http'
    domain = request.get_host() if request else settings.SITE_URL.rstrip('/').split('://')[-1]

    for user in subscribers:
        if preferences.get(user.pk) not in (None, listing.listing_type):
            continue
        context = {
            'user': user, 'listing': listing, 'site_name': settings.SITE_NAME,
            'protocol': protocol, 'domain': domain,
        }
        try:
            if user.receives_notifications and settings.EMAIL_DELIVERY_ENABLED:
                message = EmailMultiAlternatives(
                    subject=_('New on %(site)s: %(title)s') % {'site': settings.SITE_NAME, 'title': listing.title},
                    body=render_to_string('notifications/email/new_listing.txt', context),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user.email],
                )
                message.attach_alternative(
                    render_to_string('notifications/email/new_listing.html', context), 'text/html'
                )
                message.send(fail_silently=False)
        except Exception:
            logger.exception('Marketplace email delivery failed for user %s.', user.pk)
        if user.receives_notifications:
            Notification.send(
                user, NotificationType.NEW_MARKET_LISTING, title, body, listing.get_absolute_url()
            )
        _send_push(user, listing, title, body)
