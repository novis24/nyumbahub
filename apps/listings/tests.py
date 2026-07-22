from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta

from apps.accounts.models import AccountRole, CustomUser, VerificationStatus
from apps.subscriptions.models import Plan, Subscription, VideoPlanEntitlement
from apps.listings.services.video_quota import complete_reservation, reserve_video_capacity
from .forms import ListingForm
from .models import GlobalVideoStoragePolicy, Listing, ListingStatus, ListingType, ListingVideo, ListingVideoStatus, LocationPrecision, ProductCategory


def form_data(**overrides):
    data = {'title':'A listing','description':'Useful description','price':'100000','location':'Kinondoni','city':'Dar es Salaam'}
    data.update(overrides)
    return data


class LocationFormTests(TestCase):
    def test_valid_tanzania_coordinates_are_saved(self):
        form = ListingForm(form_data(latitude='-6.7924', longitude='39.2083'), listing_type=ListingType.RENTAL)
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_and_non_tanzania_coordinates_are_rejected(self):
        form = ListingForm(form_data(latitude='51.5074', longitude='-0.1278'), listing_type=ListingType.RENTAL)
        self.assertFalse(form.is_valid())
        self.assertIn('within Tanzania', str(form.errors))

    def test_omitted_coordinates_preserve_instance_values_on_edit(self):
        owner = CustomUser.objects.create_user(username='owner', email='owner@example.com', password='x', role=AccountRole.LANDLORD)
        listing = Listing.objects.create(owner=owner, listing_type=ListingType.RENTAL, title='Home', description='Home', price=1, location='Area', latitude=Decimal('-6.792400'), longitude=Decimal('39.208300'))
        form = ListingForm(form_data(latitude='', longitude=''), instance=listing, listing_type=ListingType.RENTAL)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.latitude, Decimal('-6.792400'))


class PublicTrustTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(username='verified', email='verified@example.com', password='x', role=AccountRole.LANDLORD, verification_status=VerificationStatus.VERIFIED)
        self.listing = Listing.objects.create(owner=self.owner, listing_type=ListingType.RENTAL, status=ListingStatus.ACTIVE, title='Private location', description='Home', price=1, location='Area', latitude=Decimal('-6.792411'), longitude=Decimal('39.208311'), location_precision=LocationPrecision.APPROXIMATE)

    def test_badge_uses_persisted_verification_status(self):
        self.assertEqual(self.listing.verification_badge_label, 'Verified Property Lister')
        self.owner.verification_status = VerificationStatus.PENDING
        self.owner.save(update_fields=['verification_status'])
        self.assertEqual(self.listing.verification_badge_label, '')

    def test_approximate_detail_does_not_serialize_exact_coordinates(self):
        response = self.client.get(self.listing.get_absolute_url())
        self.assertNotContains(response, '-6.792411')
        self.assertNotContains(response, '39.208311')
        self.assertContains(response, 'Approximate area')


class CategoryValidationTests(TestCase):
    def test_auto_requires_vehicle_fields_not_property_fields(self):
        form = ListingForm(form_data(vehicle_make='Toyota', vehicle_model='Vitz', vehicle_year='2020', mileage_km='10', auto_category='car', auto_condition='foreign_used'), listing_type=ListingType.AUTO)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('property_type', form.errors)

    def test_sme_requires_product_or_service(self):
        form = ListingForm(form_data(), listing_type=ListingType.SME)
        self.assertFalse(form.is_valid())
        self.assertIn('sme_kind', form.errors)


class ListingWorkflowTests(TestCase):
    def setUp(self):
        self.sme = CustomUser.objects.create_user(username='shop', email='shop@example.com', password='secret', role=AccountRole.SME)
        self.category = ProductCategory.objects.get(slug='groceries-food')
        self.client.force_login(self.sme)

    def test_sme_form_does_not_offer_other_account_categories(self):
        response = self.client.get(reverse('listings:create'))
        self.assertContains(response, 'List a product or service')
        self.assertNotContains(response, 'value="auto"')
        self.assertNotContains(response, 'value="rental"')
        self.assertNotContains(response, 'Spacious 2-bedroom apartment')

    def test_publish_status_and_role_category_make_listing_public(self):
        response = self.client.post(reverse('listings:create'), form_data(
            listing_type='auto', sme_kind='product', price_type='fixed',
            status='active', business_category='Food', product_category=self.category.id,
        ))
        listing = Listing.objects.get(owner=self.sme)
        self.assertEqual(listing.listing_type, ListingType.SME)
        self.assertEqual(listing.status, ListingStatus.ACTIVE)
        self.assertRedirects(response, listing.get_absolute_url())
        home = self.client.get(reverse('core:home') + '?type=sme')
        self.assertContains(home, listing.title)


class VideoQuotaTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(username='video', email='video@example.com', password='x', role=AccountRole.LANDLORD)
        Subscription.objects.create(user=self.owner, plan=Plan.STANDARD, is_active=True)
        VideoPlanEntitlement.objects.create(
            plan=Plan.STANDARD,
            video_uploads_allowed=True,
            max_videos_per_listing=3,
            max_video_size_mb=200,
            max_aggregate_video_storage_mb=500,
            total_video_storage_bytes=500_000_000,
            absolute_max_video_bytes=200_000_000,
            upload_enabled=True,
            recording_enabled=True,
        )
        self.listing = Listing.objects.create(owner=self.owner, listing_type=ListingType.RENTAL, title='Video home', description='Home', price=1, location='Area')
        self.policy = GlobalVideoStoragePolicy.get_solo()

    def _video(self, size):
        return ListingVideo.objects.create(
            listing=self.listing,
            owner=self.owner,
            object_key=f'listing-videos/test-{size}.mp4',
            original_filename='video.mp4',
            content_type='video/mp4',
            file_size=size,
            upload_status=ListingVideoStatus.PENDING,
            upload_expires_at=timezone.now() + timedelta(minutes=30),
        )

    def test_global_capacity_denies_reservation_without_exceeding_cap(self):
        self.policy.global_storage_cap_bytes = 100
        self.policy.committed_bytes = 80
        self.policy.reserved_bytes = 10
        self.policy.save()

        reservation, error = reserve_video_capacity(user=self.owner, listing=self.listing, video=self._video(20), declared_size=20)

        self.assertIsNone(reservation)
        self.assertIn('temporarily unavailable', error)
        self.policy.refresh_from_db()
        self.assertEqual(self.policy.reserved_bytes, 10)

    def test_completion_is_idempotent_and_commits_once(self):
        self.policy.global_storage_cap_bytes = 1_000
        self.policy.committed_bytes = 0
        self.policy.reserved_bytes = 0
        self.policy.save()
        reservation, error = reserve_video_capacity(user=self.owner, listing=self.listing, video=self._video(100), declared_size=100)
        self.assertFalse(error)

        complete_reservation(reservation, 100)
        complete_reservation(reservation, 100)

        self.policy.refresh_from_db()
        self.assertEqual(self.policy.committed_bytes, 100)
        self.assertEqual(self.policy.reserved_bytes, 0)
