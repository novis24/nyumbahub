from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms

from .models import Listing, ListingReview, ListingType, SMEDetails, VehicleDetails


TANZANIA_BOUNDS = {'lat_min': Decimal('-12'), 'lat_max': Decimal('-0.5'), 'lng_min': Decimal('28.5'), 'lng_max': Decimal('41.5')}
AUTO_FEATURES = [('air_conditioning','Air conditioning'),('abs','ABS'),('airbags','Airbags'),('power_steering','Power steering'),('power_windows','Power windows'),('central_locking','Central locking'),('reverse_camera','Reverse camera'),('parking_sensors','Parking sensors'),('bluetooth','Bluetooth'),('navigation','Navigation system'),('leather_seats','Leather seats'),('sunroof','Sunroof'),('alloy_wheels','Alloy wheels'),('four_wheel_drive','Four-wheel drive'),('keyless_entry','Keyless entry')]


class ListingForm(forms.ModelForm):
    auto_category = forms.ChoiceField(choices=VehicleDetails._meta.get_field('category').choices, required=False)
    auto_condition = forms.ChoiceField(choices=VehicleDetails._meta.get_field('condition').choices, required=False)
    auto_features = forms.MultipleChoiceField(choices=AUTO_FEATURES, widget=forms.CheckboxSelectMultiple, required=False)
    sme_kind = forms.ChoiceField(choices=SMEDetails._meta.get_field('kind').choices, required=False)
    price_type = forms.ChoiceField(choices=SMEDetails._meta.get_field('price_type').choices, required=False)

    class Meta:
        model = Listing
        fields = ['title','description','price','location','city','latitude','longitude','nearby_landmark','location_precision','property_type','bedrooms','bathrooms','floor_number','is_furnished','allows_students','business_category','is_for_sale','vehicle_make','vehicle_model','vehicle_year','mileage_km']
        widgets = {'description': forms.Textarea(attrs={'rows': 5}), 'latitude': forms.HiddenInput(), 'longitude': forms.HiddenInput()}

    def __init__(self, *args, listing_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.listing_type = listing_type or getattr(self.instance, 'listing_type', None) or ListingType.RENTAL
        self.fields['location_precision'].required = False
        for name in ('title','description','price','location'):
            self.fields[name].required = True
        if self.instance.pk:
            if self.listing_type == ListingType.AUTO and hasattr(self.instance, 'vehicle_details'):
                detail = self.instance.vehicle_details
                self.fields['auto_category'].initial = detail.category
                self.fields['auto_condition'].initial = detail.condition
                self.fields['auto_features'].initial = detail.features_list
            if self.listing_type == ListingType.SME and hasattr(self.instance, 'sme_details'):
                self.fields['sme_kind'].initial = self.instance.sme_details.kind
                self.fields['price_type'].initial = self.instance.sme_details.price_type

    def clean(self):
        cleaned = super().clean()
        cleaned['location_precision'] = cleaned.get('location_precision') or 'approximate'
        lat, lng = cleaned.get('latitude'), cleaned.get('longitude')
        if self.listing_type == ListingType.RENTAL:
            if self.instance.pk and lat is None and lng is None:
                lat, lng = self.instance.latitude, self.instance.longitude
                cleaned['latitude'], cleaned['longitude'] = lat, lng
            # Blank coordinates remain supported for legacy listings; if one is supplied both are required.
            if (lat is None) != (lng is None):
                raise forms.ValidationError('Please select a complete location on the map.')
            if lat is not None:
                if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    raise forms.ValidationError('The selected map coordinates are invalid.')
                if not (TANZANIA_BOUNDS['lat_min'] <= lat <= TANZANIA_BOUNDS['lat_max'] and TANZANIA_BOUNDS['lng_min'] <= lng <= TANZANIA_BOUNDS['lng_max']):
                    raise forms.ValidationError('Please select a location within Tanzania.')
        if self.listing_type == ListingType.AUTO:
            year = cleaned.get('vehicle_year')
            if year and not 1886 <= year <= date.today().year + 1:
                self.add_error('vehicle_year', 'Enter a realistic manufacturing year.')
            if not cleaned.get('vehicle_make') or not cleaned.get('vehicle_model'):
                raise forms.ValidationError('Vehicle make and model are required.')
            if not cleaned.get('auto_category') or not cleaned.get('auto_condition'):
                raise forms.ValidationError('Vehicle category and condition are required.')
        if self.listing_type == ListingType.SME and not cleaned.get('sme_kind'):
            self.add_error('sme_kind', 'Choose whether this is a product or service.')
        return cleaned

    def save_details(self, listing):
        if self.listing_type == ListingType.AUTO:
            VehicleDetails.objects.update_or_create(listing=listing, defaults={'category': self.cleaned_data['auto_category'], 'condition': self.cleaned_data['auto_condition'], 'features': ','.join(self.cleaned_data.get('auto_features', []))})
        elif self.listing_type == ListingType.SME:
            SMEDetails.objects.update_or_create(listing=listing, defaults={'kind': self.cleaned_data['sme_kind'], 'price_type': self.cleaned_data.get('price_type') or 'fixed'})


class ListingReviewForm(forms.ModelForm):
    class Meta:
        model = ListingReview
        fields = ['rating', 'comment']
        widgets = {'rating': forms.Select(choices=[(5,'5 stars'),(4,'4 stars'),(3,'3 stars'),(2,'2 stars'),(1,'1 star')]), 'comment': forms.Textarea(attrs={'rows':4})}
