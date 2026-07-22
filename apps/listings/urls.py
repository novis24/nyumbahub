from django.urls import path
from . import views

app_name = 'listings'

urlpatterns = [
    path('create/', views.create_listing, name='create'),
    path('providers/<int:owner_id>/', views.provider_gallery, name='provider_gallery'),
    path('cart/', views.cart_page, name='cart'),
    path('cart/state/', views.cart_state, name='cart_state'),
    path('cart/add/<uuid:listing_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/items/<int:item_id>/', views.update_cart_item, name='update_cart_item'),
    path('cart/clear/', views.clear_cart, name='clear_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('orders/<int:order_id>/<uuid:access_key>/', views.order_detail, name='order_detail'),
    path('videos/upload-session/', views.create_video_upload, name='create_video_upload'),
    path('videos/<uuid:video_id>/complete/', views.complete_video_upload, name='complete_video_upload'),
    path('videos/<uuid:video_id>/playback-url/', views.video_playback_url, name='video_playback_url'),
    path('videos/<uuid:video_id>/delete/', views.delete_video, name='delete_video'),
    path('mine/', views.my_listings, name='my_listings'),
    path('saved/', views.saved_listings, name='saved'),
    path('<slug:slug>/', views.listing_detail, name='detail'),
    path('<slug:slug>/reviews/', views.submit_review, name='submit_review'),
    path('<slug:slug>/edit/', views.edit_listing, name='edit'),
    path('<slug:slug>/delete/', views.delete_listing, name='delete'),
    path('save/<uuid:listing_id>/', views.toggle_save, name='toggle_save'),
]
