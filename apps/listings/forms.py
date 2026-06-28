from django import forms
from .models import Listing, ListingReview, PropertyType


class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = [
            'title', 'description', 'price', 'location', 'city',
            'property_type', 'bedrooms', 'bathrooms', 'floor_number',
            'is_furnished', 'allows_students',
            'business_category', 'is_for_sale',
            'vehicle_make', 'vehicle_model', 'vehicle_year', 'mileage_km',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # All fields are optional at the form level;
        # validation logic lives in the view based on listing_type.
        for field in self.fields.values():
            field.required = False
        self.fields['title'].required = True
        self.fields['price'].required = True
        self.fields['location'].required = True
        self.fields['description'].required = True


class ListingReviewForm(forms.ModelForm):
    class Meta:
        model = ListingReview
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(
                choices=[(5, '5 stars'), (4, '4 stars'), (3, '3 stars'), (2, '2 stars'), (1, '1 star')]
            ),
            'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Share your experience with this owner or listing.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rating'].required = True
        self.fields['comment'].required = False
