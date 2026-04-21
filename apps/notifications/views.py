from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from .models import Notification


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
