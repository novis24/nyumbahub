from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

from .models import Cart, CartItem, HeroGroup, HeroImage, ListingReview, ProductAttribute, ProductCategory, SMEOrder, SMEOrderItem


class HeroImageInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        active_forms = [
            form
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False)
        ]
        if len(active_forms) > 5:
            raise ValidationError(_('A hero group can contain a maximum of five images.'))


class HeroImageInline(admin.TabularInline):
    model = HeroImage
    formset = HeroImageInlineFormSet
    extra = 1
    max_num = 5
    fields = ('image', 'alt_text', 'order')


class ProductSubcategoryInline(admin.TabularInline):
    model = ProductCategory
    fk_name = 'parent'
    extra = 1
    fields = ('name', 'slug', 'is_active', 'order')
    prepopulated_fields = {'slug': ('name',)}


class ProductAttributeInline(admin.TabularInline):
    model = ProductAttribute
    extra = 1
    fields = ('name', 'slug', 'input_type', 'choices', 'is_filterable', 'order')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(HeroGroup)
class HeroGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'order', 'rotation_seconds', 'group_duration_seconds')
    list_editable = ('is_active', 'order', 'rotation_seconds', 'group_duration_seconds')
    inlines = [HeroImageInline]


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'is_active', 'order')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'slug', 'parent__name')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductSubcategoryInline, ProductAttributeInline]


@admin.register(SMEOrder)
class SMEOrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'customer_phone', 'status', 'total', 'created_at')
    list_filter = ('status', 'fulfillment_method', 'created_at')
    search_fields = ('customer_name', 'customer_phone', 'customer_email')


admin.site.register(ListingReview)
admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(SMEOrderItem)
