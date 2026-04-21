def global_context(request):
    ctx = {
        'site_name': 'NyumbaHub',
        'unread_notifications_count': 0,
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
