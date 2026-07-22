from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _
from .models import CustomUser, AccountRole, KYCDocument
from phonenumber_field.formfields import PhoneNumberField


class RoleSelectForm(forms.Form):
    """
    Step 1 of signup — user picks their account type.
    Progressive disclosure: the rest of the form depends on this choice.
    """
    ROLE_CHOICES = [
        (AccountRole.SEEKER, _('I am looking for a house')),
        (AccountRole.LANDLORD, _('I want to list my property for rent')),
        (AccountRole.SME, _('I run a small business / shop')),
        (AccountRole.AUTO, _('I sell vehicles')),
    ]
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.RadioSelect,
    )


class SignupForm(UserCreationForm):
    """
    Full signup form — shown after role is selected.
    Fields adapt slightly based on role (handled in the template/view).
    """
    first_name = forms.CharField(max_length=60, required=True)
    last_name = forms.CharField(max_length=60, required=True)
    email = forms.EmailField(required=True)
    phone = PhoneNumberField(
        region='TZ',
        required=False,
        help_text=_('e.g. +255 712 345 678'),
    )
    location = forms.CharField(
        max_length=120,
        required=False,
        help_text=_('City or district'),
    )
    role = forms.CharField(widget=forms.HiddenInput)
    agree_terms = forms.BooleanField(required=True)
    agree_updates = forms.BooleanField(required=False)

    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'email', 'username',
            'phone', 'location', 'role', 'password1', 'password2',
        ]

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError(_('An account with this email already exists.'))
        return email

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and CustomUser.objects.filter(phone=phone).exists():
            raise forms.ValidationError(_('An account with this phone number already exists.'))
        return phone or None

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = self.cleaned_data['role']
        user.location = self.cleaned_data.get('location', '')
        user.receives_notifications = self.cleaned_data.get('agree_updates', False)
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': _('We could not sign you in with that email and password. Please check both and try again.'),
        'inactive': _('This account has been disabled. Please contact support if you need help.'),
    }
    username = forms.EmailField(
        label=_('Email address'),
        widget=forms.EmailInput(attrs={'autofocus': True, 'placeholder': 'you@email.com'}),
    )
    password = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'}),
    )


class ProfileUpdateForm(forms.ModelForm):
    """
    Progressive — shown inside account settings, not on signup.
    """
    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'phone', 'bio', 'avatar', 'location',
            'shop_name', 'shop_location', 'nearby_names', 'public_phone',
            'whatsapp_phone', 'website_url', 'facebook_url', 'instagram_url', 'tiktok_url',
        ]
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3, 'maxlength': 500}),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and CustomUser.objects.filter(phone=phone).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_('An account with this phone number already exists.'))
        return phone or None


class PasswordChangeRequestForm(forms.Form):
    """Shown only when user explicitly navigates to security settings."""
    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('new_password')
        p2 = cleaned.get('confirm_password')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError(_('New passwords do not match.'))
        return cleaned


class KYCSubmitForm(forms.ModelForm):
    """
    Landlord/SME/Auto verification — progressive, surfaced only when
    user tries to submit their first listing without being verified.
    """
    class Meta:
        model = KYCDocument
        fields = ['doc_type', 'document_front', 'document_back', 'selfie']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['document_back'].required = False
        self.fields['selfie'].required = False
