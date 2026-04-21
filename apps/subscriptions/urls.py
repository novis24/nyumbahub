from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('plans/', views.choose_plan, name='choose_plan'),
    path('payment/<str:plan>/', views.payment, name='payment'),
    path('manage/', views.manage, name='manage'),
]
