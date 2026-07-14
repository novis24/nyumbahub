from django.test import TestCase

from .forms import SignupForm
from .models import CustomUser


class PhoneUniquenessTests(TestCase):
    def setUp(self):
        CustomUser.objects.create_user(
            username='existing', email='existing@example.com', password='StrongPass123!',
            phone='+255712345678',
        )

    def test_signup_rejects_equivalent_existing_phone(self):
        form = SignupForm(data={
            'first_name': 'Amina', 'last_name': 'Juma', 'username': 'amina',
            'email': 'amina@example.com', 'phone': '0712 345 678', 'location': 'Dar es Salaam',
            'role': 'seeker', 'password1': 'A-Strong-Pass-123!',
            'password2': 'A-Strong-Pass-123!', 'agree_terms': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_blank_phone_is_stored_as_null(self):
        form = SignupForm(data={
            'first_name': 'Amina', 'last_name': 'Juma', 'username': 'amina',
            'email': 'amina@example.com', 'phone': '', 'location': '', 'role': 'seeker',
            'password1': 'A-Strong-Pass-123!', 'password2': 'A-Strong-Pass-123!',
            'agree_terms': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().phone)
