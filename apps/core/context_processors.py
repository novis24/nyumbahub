from django.conf import settings


def global_context(request):
    listing_type = request.GET.get('type', '')
    path = request.path
    show_sme_cart = (
        listing_type == 'sme'
        or '/cart/' in path
        or '/checkout/' in path
        or '/orders/' in path
    )
    ctx = {
        'site_name': settings.SITE_NAME,
        'unread_notifications_count': 0,
        'payments_enabled': settings.PAYMENTS_ENABLED,
        'firebase_config': {
            'apiKey': settings.FIREBASE_API_KEY,
            'authDomain': settings.FIREBASE_AUTH_DOMAIN,
            'projectId': settings.FIREBASE_PROJECT_ID,
            'storageBucket': settings.FIREBASE_STORAGE_BUCKET,
            'messagingSenderId': settings.FIREBASE_MESSAGING_SENDER_ID,
            'appId': settings.FIREBASE_APP_ID,
            'vapidKey': settings.FIREBASE_VAPID_KEY,
        },
        'show_sme_cart': show_sme_cart,
        'cart_count': 0,
    }
    try:
        from apps.listings.views import cart_for_request, cart_payload
        if show_sme_cart:
            ctx['cart_count'] = cart_payload(cart_for_request(request))['count']
    except Exception:
        pass
    if request.user.is_authenticated:
        try:
            from apps.notifications.models import Notification
            ctx['unread_notifications_count'] = Notification.objects.filter(
                user=request.user, is_read=False,
            ).count()
        except Exception:
            pass
    return ctx
