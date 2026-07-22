from django.contrib import admin

from .models import Cart, CartItem, HeroGroup, HeroImage, ListingReview, SMEOrder, SMEOrderItem


class HeroImageInline(admin.TabularInline):
    model = HeroImage
    extra = 1
    max_num = 5
    fields = ('image', 'alt_text', 'order')


@admin.register(HeroGroup)
class HeroGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'order', 'rotation_seconds', 'group_duration_seconds')
    list_editable = ('is_active', 'order', 'rotation_seconds', 'group_duration_seconds')
    inlines = [HeroImageInline]


@admin.register(SMEOrder)
class SMEOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'customer_phone', 'status', 'total', 'created_at')
    list_filter = ('status', 'fulfillment_method', 'created_at')
    search_fields = ('customer_name', 'customer_phone', 'customer_email')


admin.site.register(ListingReview)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(SMEOrderItem)
