from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from .models import Notification, PushDevice


@login_required
def notification_list(request):
    notifications = request.user.notifications.all()[:50]
    # Mark all as read on view
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'notifications/list.html', {
        'notifications': notifications,
    })


@login_required
@require_POST
def mark_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.is_read = True
    n.save(update_fields=['is_read'])
    if request.htmx:
        return HttpResponse('')
    return render(request, 'notifications/list.html')


@login_required
@require_POST
def register_push_device(request):
    import json
    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request.'}, status=400)
    token = str(payload.get('token', '')).strip()
    if not token or len(token) > 4096:
        return JsonResponse({'error': 'A valid device token is required.'}, status=400)
    PushDevice.objects.update_or_create(
        token=token,
        defaults={'user': request.user, 'is_active': True},
    )
    if not request.user.receives_push_notifications:
        request.user.receives_push_notifications = True
        request.user.save(update_fields=['receives_push_notifications'])
    return JsonResponse({'registered': True})


@login_required
@require_POST
def unregister_push_devices(request):
    request.user.push_devices.update(is_active=False)
    request.user.receives_push_notifications = False
    request.user.save(update_fields=['receives_push_notifications'])
    return JsonResponse({'registered': False})
