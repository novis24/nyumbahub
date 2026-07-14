from django.conf import settings


def global_context(request):
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
    }
    if request.user.is_authenticated:
        try:
            from apps.notifications.models import Notification
            ctx['unread_notifications_count'] = Notification.objects.filter(
                user=request.user, is_read=False,
            ).count()
        except Exception:
            pass
    return ctx
