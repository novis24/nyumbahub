from django.conf import settings


def global_context(request):
    ctx = {
        'site_name': settings.SITE_NAME,
        'unread_notifications_count': 0,
        'payments_enabled': settings.PAYMENTS_ENABLED,
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
