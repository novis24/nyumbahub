from pathlib import Path
import json
import struct

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccountRole, CustomUser
from apps.listings.models import Listing, ListingStatus, ListingType


class HomePageTests(TestCase):
    def test_minimal_home_page_renders_on_mobile_and_desktop_markup(self):
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Find spaces that')
        self.assertContains(response, 'data-install-app')

    def test_install_button_is_hidden_by_default(self):
        response = self.client.get(reverse('core:home'))
        html = response.content.decode()
        self.assertIn('data-install-app onclick="installISellApp()" hidden', html)
        self.assertIn('data-install-fallback hidden', html)

    def test_service_worker_controls_the_full_app_scope(self):
        response = self.client.get(reverse('core:service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertEqual(response['Content-Type'], 'application/javascript')
        body = b''.join(response.streaming_content)
        self.assertGreater(len(body.strip()), 100)
        self.assertIn(b"self.addEventListener('fetch'", body)

    def test_home_registers_service_worker_from_root_scope(self):
        response = self.client.get(reverse('core:home'))
        html = response.content.decode()
        self.assertIn("navigator.serviceWorker.register('/sw.js', {scope:'/'})", html)

    def test_manifest_is_available_and_installable(self):
        manifest_path = Path(settings.BASE_DIR) / 'static' / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest['name'], 'iSellTZ Marketplace')
        self.assertEqual(manifest['short_name'], 'iSellTZ')
        self.assertEqual(manifest['start_url'], '/?source=pwa')
        self.assertEqual(manifest['scope'], '/')
        self.assertEqual(manifest['display'], 'standalone')
        self.assertRegex(manifest['theme_color'], r'^#[0-9a-fA-F]{6}$')
        self.assertRegex(manifest['background_color'], r'^#[0-9a-fA-F]{6}$')

        icons = {icon['sizes']: icon for icon in manifest['icons']}
        self.assertEqual(icons['192x192']['src'], '/static/icons/icon-192.png')
        self.assertEqual(icons['512x512']['src'], '/static/icons/icon-512.png')
        self.assertIn('maskable', icons['512x512']['purpose'])

    def test_required_pwa_icons_exist_at_declared_sizes(self):
        expected_sizes = {
            'icon-192.png': (192, 192),
            'icon-512.png': (512, 512),
        }
        for filename, expected in expected_sizes.items():
            with self.subTest(filename=filename):
                path = Path(settings.BASE_DIR) / 'static' / 'icons' / filename
                self.assertTrue(path.exists())
                with path.open('rb') as image:
                    image.seek(16)
                    width, height = struct.unpack('>II', image.read(8))
                self.assertEqual((width, height), expected)


class BilingualInterfaceTests(TestCase):
    full_shell_english_markers = [
        'Home',
        'Search',
        'Privacy Policy',
        'Terms of Service',
        'Trusted Rentals & Estate platform',
    ]
    full_shell_swahili_markers = [
        'Nyumbani',
        'Tafuta',
        'Sera ya faragha',
        'Masharti ya huduma',
        'Jukwaa la kuaminika la upangishaji na mali',
    ]

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='amina',
            email='amina@example.com',
            password='StrongPass123!',
            role=AccountRole.LANDLORD,
        )

    def assert_language_shell(self, url, language, expected):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(f'<html lang="{language}"', html)
        self.assertIn('name="language"', html)
        self.assertIn('<option value="en"', html)
        self.assertIn('<option value="sw"', html)
        for marker in expected:
            self.assertIn(marker, html)

    def test_public_app_shell_pages_render_consistently_in_both_languages(self):
        public_urls = [
            reverse('core:home'),
            reverse('search:results'),
        ]
        for url in public_urls:
            with self.subTest(url=url, language='en'):
                self.assert_language_shell(url, 'en', self.full_shell_english_markers)
            with self.subTest(url=url, language='sw'):
                self.assert_language_shell(url, 'sw', self.full_shell_swahili_markers)

    def test_auth_pages_keep_global_toggle_and_translate_auth_copy(self):
        markers = {
            'en': ['Sign in', 'Email address', 'Password', "Don't have an account?"],
            'sw': ['Ingia', 'Barua pepe', 'Nenosiri', 'Huna akaunti?'],
        }
        for language, expected in markers.items():
            with self.subTest(language=language):
                self.assert_language_shell(reverse('accounts:login'), language, expected)

    def test_home_hero_and_section_labels_switch_to_swahili(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sw'
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        expected = [
            'Maarufu karibu nawe',
            'Taarifa mpya za watoa huduma',
            'Matangazo ya hivi karibuni',
            'Tafuta kinachosogeza',
            'Nyumba za kupanga',
            'Maduka ya biashara ndogo',
            'Vichujio',
        ]
        forbidden = [
            'Popular near you',
            'Fresh provider updates',
            'Recent listings',
            'Find what moves',
            'Rentals',
            'SME Shops',
            'Use current location',
            'Allow location',
            'data-use-location',
        ]
        for marker in expected:
            self.assertIn(marker, html)
        for marker in forbidden:
            self.assertNotIn(marker, html)
        self.assertEqual(html.count('name="language"'), 1)

    def test_authenticated_portal_shell_renders_consistently_in_both_languages(self):
        self.client.force_login(self.user)
        portal_urls = [
            reverse('accounts:profile'),
            reverse('accounts:settings'),
            reverse('listings:my_listings'),
            reverse('notifications:list'),
        ]
        for url in portal_urls:
            with self.subTest(url=url, language='en'):
                self.assert_language_shell(url, 'en', self.full_shell_english_markers)
            with self.subTest(url=url, language='sw'):
                self.assert_language_shell(url, 'sw', self.full_shell_swahili_markers)

    def test_language_toggle_sets_session_and_cookie(self):
        response = self.client.post(reverse('set_language'), {'language': 'sw', 'next': reverse('core:home')})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'sw')
        response = self.client.get(reverse('core:home'))
        html = response.content.decode()
        self.assertIn('<html lang="sw"', html)
        self.assertIn('Nyumbani', html)

    def test_language_cookie_persists_across_navigation_and_switches_back(self):
        Listing.objects.create(
            owner=self.user,
            listing_type=ListingType.RENTAL,
            status=ListingStatus.ACTIVE,
            title='Mikocheni apartment',
            description='Bright apartment near shops.',
            price=450000,
            location='Mikocheni',
            city='Dar es Salaam',
            bedrooms=2,
            bathrooms=1,
        )
        response = self.client.post(reverse('set_language'), {'language': 'sw', 'next': reverse('accounts:profile')})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'sw')

        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'sw'
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:profile'))
        html = response.content.decode()
        self.assertIn('<html lang="sw"', html)
        self.assertIn('Nyumbani', html)

        response = self.client.get(reverse('notifications:list'))
        html = response.content.decode()
        self.assertIn('<html lang="sw"', html)
        self.assertIn('Nyumbani', html)

        response = self.client.post(reverse('set_language'), {'language': 'en', 'next': reverse('accounts:profile')})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'en')
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = 'en'
        response = self.client.get(reverse('accounts:profile'))
        html = response.content.decode()
        self.assertIn('<html lang="en"', html)
        self.assertIn('Home', html)

    def test_language_sensitive_html_varies_by_accept_language_and_cookie(self):
        response = self.client.get(reverse('core:home'))
        vary = {value.strip() for value in response.get('Vary', '').split(',')}
        self.assertIn('Accept-Language', vary)
        self.assertIn('Cookie', vary)

    def test_service_worker_does_not_cache_language_specific_html(self):
        response = self.client.get(reverse('core:service_worker'))
        body = b''.join(response.streaming_content).decode()
        self.assertIn("url.pathname.startsWith('/static/')", body)
        self.assertNotIn("navigate", body)
        self.assertNotIn("text/html", body)

    def test_locale_catalogs_are_compiled_and_have_no_empty_swahili_entries(self):
        locale_dir = Path(settings.LOCALE_PATHS[0]) / 'sw' / 'LC_MESSAGES'
        self.assertTrue((locale_dir / 'django.mo').exists())
        po = (locale_dir / 'django.po').read_text()
        blocks = [block for block in po.split('\n\n') if not block.startswith('# SOME DESCRIPTIVE TITLE')]
        empty_blocks = []
        for block in blocks:
            if 'msgid ""' in block:
                continue
            lines = block.splitlines()
            try:
                index = next(i for i, line in enumerate(lines) if line.startswith('msgstr '))
            except StopIteration:
                continue
            rendered = ''.join(line.strip()[1:-1] for line in lines[index:] if line.strip().startswith('"'))
            if lines[index] == 'msgstr ""' and not rendered:
                empty_blocks.append(block)
        self.assertEqual(empty_blocks, [])
