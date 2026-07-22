from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AccountRole, CustomUser


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
