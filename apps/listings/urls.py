from django.urls import path
from . import views

app_name = 'listings'

urlpatterns = [
    path('create/', views.create_listing, name='create'),
    path('mine/', views.my_listings, name='my_listings'),
    path('saved/', views.saved_listings, name='saved'),
    path('<slug:slug>/', views.listing_detail, name='detail'),
    path('<slug:slug>/reviews/', views.submit_review, name='submit_review'),
    path('<slug:slug>/edit/', views.edit_listing, name='edit'),
    path('<slug:slug>/delete/', views.delete_listing, name='delete'),
    path('save/<uuid:listing_id>/', views.toggle_save, name='toggle_save'),
]
