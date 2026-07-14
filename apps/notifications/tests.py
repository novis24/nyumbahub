from django.test import TestCase

from apps.accounts.models import CustomUser
from apps.listings.models import Listing, ListingStatus, ListingType, ListingView
from .services import _preferred_listing_types


class MarketplacePreferenceTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(username='owner', email='owner@example.com', password='x')
        self.seeker = CustomUser.objects.create_user(username='seeker', email='seeker@example.com', password='x')

    def listing(self, kind, title):
        return Listing.objects.create(
            owner=self.owner, listing_type=kind, status=ListingStatus.ACTIVE,
            title=title, description='Description', price=100000, location='Kinondoni',
        )

    def test_most_viewed_category_is_preferred(self):
        rental_one = self.listing(ListingType.RENTAL, 'Rental one')
        rental_two = self.listing(ListingType.RENTAL, 'Rental two')
        auto = self.listing(ListingType.AUTO, 'Auto')
        for index, listing in enumerate((rental_one, rental_two, auto)):
            ListingView.objects.create(
                listing=listing, user=self.seeker, viewer_token=f'user:{self.seeker.pk}:{index}'
            )
        preferences = _preferred_listing_types([self.seeker.pk])
        self.assertEqual(preferences[self.seeker.pk], ListingType.RENTAL)
