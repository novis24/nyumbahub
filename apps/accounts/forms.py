from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, AccountRole, KYCDocument


class RoleSelectForm(forms.Form):
    """
    Step 1 of signup — user picks their account type.
    Progressive disclosure: the rest of the form depends on this choice.
    """
    ROLE_CHOICES = [
        (AccountRole.SEEKER, 'I am looking for a house'),
        (AccountRole.LANDLORD, 'I want to list my property for rent'),
        (AccountRole.SME, 'I run a small business / shop'),
        (AccountRole.AUTO, 'I sell vehicles'),
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
    phone = forms.CharField(
        max_length=20,
        required=False,
        help_text='e.g. +255 712 345 678',
    )
    location = forms.CharField(
        max_length=120,
        required=False,
        help_text='City or district',
    )
    role = forms.CharField(widget=forms.HiddenInput)
    agree_terms = forms.BooleanField(required=True)

    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'email', 'username',
            'phone', 'location', 'role', 'password1', 'password2',
        ]

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = self.cleaned_data['role']
        user.location = self.cleaned_data.get('location', '')
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email address',
        widget=forms.EmailInput(attrs={'autofocus': True, 'placeholder': 'you@email.com'}),
    )
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': '••••••••'}),
    )


class ProfileUpdateForm(forms.ModelForm):
    """
    Progressive — shown inside account settings, not on signup.
    """
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'phone', 'bio', 'avatar', 'location']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3, 'maxlength': 500}),
        }


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
            raise forms.ValidationError('New passwords do not match.')
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
