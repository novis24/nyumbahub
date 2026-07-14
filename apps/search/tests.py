from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.listings.models import Listing, ListingStatus, ListingType, VehicleDetails


class SearchResultsTests(TestCase):
    def setUp(self):
        owner = CustomUser.objects.create_user(username='dealer', email='dealer@example.com', password='x')
        self.auto = Listing.objects.create(
            owner=owner, listing_type=ListingType.AUTO, status=ListingStatus.ACTIVE,
            title='Toyota Harrier', description='Clean vehicle', price=32000000,
            location='Ilala', city='Dar es Salaam', vehicle_make='Toyota',
            vehicle_model='Harrier', vehicle_year=2020,
        )
        VehicleDetails.objects.create(listing=self.auto, category='car', condition='foreign_used')

    def test_htmx_partial_exists_and_renders(self):
        response = self.client.get(
            reverse('search:results'),
            {'partial': '1', 'type': 'auto', 'vehicle_make': 'Toyota'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'partials/search_results_grid.html')
        self.assertContains(response, 'Toyota Harrier')

    def test_auto_condition_filter(self):
        response = self.client.get(reverse('search:results'), {
            'type': 'auto', 'vehicle_condition': 'new',
        })
        self.assertNotContains(response, 'Toyota Harrier')
