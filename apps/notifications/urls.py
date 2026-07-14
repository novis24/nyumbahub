from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list, name='list'),
    path('<int:pk>/read/', views.mark_read, name='mark_read'),
    path('push/register/', views.register_push_device, name='push_register'),
    path('push/unregister/', views.unregister_push_devices, name='push_unregister'),
]
