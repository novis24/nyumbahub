from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_minimal_home_page_renders_on_mobile_and_desktop_markup(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Find spaces that')
        self.assertContains(response, 'data-install-app')

    def test_service_worker_controls_the_full_app_scope(self):
        response = self.client.get(reverse('core:service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertEqual(response['Content-Type'], 'application/javascript')
