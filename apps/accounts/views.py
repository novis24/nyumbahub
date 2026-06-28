from smtplib import SMTPException

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from .forms import (
    RoleSelectForm, SignupForm, LoginForm,
    ProfileUpdateForm, PasswordChangeRequestForm, KYCSubmitForm
)
from .models import CustomUser, KYCDocument
from apps.listings.models import Listing, ListingReview, ListingStatus
from apps.listings.models import SavedListing
from django.db.models import Avg, Count


# ─── Auth ─────────────────────────────────────────────────

def signup_role(request):
    """
    Step 1: user picks their role.
    On POST — if valid, redirect to step 2 carrying role in session.
    """
    if request.user.is_authenticated:
        return redirect('core:home')

    form = RoleSelectForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        request.session['signup_role'] = form.cleaned_data['role']
        return redirect('accounts:signup')

    return render(request, 'accounts/signup_role.html', {'form': form})


def signup(request):
    """Step 2: fill in name, email, password."""
    if request.user.is_authenticated:
        return redirect('core:home')

    role = request.session.get('signup_role')
    if not role:
        return redirect('accounts:signup_role')

    form = SignupForm(request.POST or None, initial={'role': role})
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f'Welcome to iSell, {user.first_name}!')
        # Clear session key
        request.session.pop('signup_role', None)
        if user.is_provider and settings.PAYMENTS_ENABLED:
            return redirect('subscriptions:choose_plan')
        return redirect('core:home')

    return render(request, 'accounts/signup.html', {
        'form': form,
        'role': role,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:home')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        next_url = request.GET.get('next', 'core:home')
        return redirect(next_url)

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('core:home')


def forgot_password(request):
    """Standalone password reset — progressive, reached via settings or login."""
    from django.contrib.auth.forms import PasswordResetForm
    form = PasswordResetForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            form.save(
                request=request,
                use_https=request.is_secure(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                subject_template_name='accounts/email/password_reset_subject.txt',
                email_template_name='accounts/email/password_reset.txt',
                html_email_template_name='accounts/email/password_reset.html',
            )
            return render(request, 'accounts/forgot_password_done.html')
        except SMTPException:
            messages.error(
                request,
                'Password reset email could not be sent. Please verify the SMTP account settings and try again.',
            )
    return render(request, 'accounts/forgot_password.html', {'form': form})


# ─── Profile ──────────────────────────────────────────────

@login_required
def profile(request):
    """Public-facing profile page."""
    return _render_profile(request, request.user)


def public_profile(request, username):
    profile_user = get_object_or_404(CustomUser, username=username)
    return _render_profile(request, profile_user)


@login_required
def profile_edit(request):
    """Edit basic profile info — name, bio, avatar, location."""
    form = ProfileUpdateForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        if request.htmx:
            return HttpResponse('<span class="text-green-600 text-sm">Saved.</span>')
        messages.success(request, 'Profile updated.')
        return redirect('accounts:profile')

    return render(request, 'accounts/profile_edit.html', {'form': form})


def _render_profile(request, profile_user):
    listings = (
        Listing.objects.filter(owner=profile_user, status=ListingStatus.ACTIVE)
        .prefetch_related('images', 'reviews')
        .order_by('-is_featured', '-created_at')
    )
    review_stats = ListingReview.objects.filter(listing__owner=profile_user).aggregate(
        average_rating=Avg('rating'),
        total_reviews=Count('id'),
    )
    recent_reviews = (
        ListingReview.objects.filter(listing__owner=profile_user)
        .select_related('reviewer', 'listing')
        .exclude(comment='')
        .order_by('-created_at')[:5]
    )
    saved_ids = set()
    if request.user.is_authenticated:
        saved_ids = set(
            SavedListing.objects.filter(user=request.user).values_list('listing_id', flat=True)
        )
    return render(request, 'accounts/profile.html', {
        'profile_user': profile_user,
        'profile_listings': listings,
        'owner_review_stats': {
            'average_rating': review_stats['average_rating'] or 0,
            'total_reviews': review_stats['total_reviews'] or 0,
        },
        'recent_reviews': recent_reviews,
        'saved_ids': saved_ids,
    })


# ─── Settings (progressive disclosure) ────────────────────

@login_required
def settings_overview(request):
    """
    Account settings landing — shows top-level categories only.
    Deeper options (password, verification, subscription, notifications)
    are revealed only when the user navigates into them.
    """
    return render(request, 'accounts/settings.html')


@login_required
def settings_security(request):
    """Password change — only visible inside security settings."""
    form = PasswordChangeRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = request.user
        if not user.check_password(form.cleaned_data['current_password']):
            form.add_error('current_password', 'Current password is incorrect.')
        else:
            user.set_password(form.cleaned_data['new_password'])
            user.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed.')
            return redirect('accounts:settings')
    return render(request, 'accounts/settings_security.html', {'form': form})


@login_required
def settings_notifications(request):
    if request.method == 'POST':
        request.user.receives_notifications = 'receives_notifications' in request.POST
        request.user.save(update_fields=['receives_notifications'])
        if request.htmx:
            return HttpResponse('<span class="text-green-600 text-sm">Saved.</span>')
        messages.success(request, 'Notification preferences updated.')
    return render(request, 'accounts/settings_notifications.html')


# ─── KYC Verification ─────────────────────────────────────

@login_required
def kyc_submit(request):
    """
    Provider verification — scaffold is ready.
    Currently optional; can be enforced by setting REQUIRE_KYC=True.
    """
    if not request.user.is_provider:
        return redirect('core:home')

    existing = getattr(request.user, 'kyc', None)
    if existing and existing.status == 'pending':
        return render(request, 'accounts/kyc_pending.html', {'kyc': existing})

    form = KYCSubmitForm(request.POST or None, request.FILES or None, instance=existing)
    if request.method == 'POST' and form.is_valid():
        kyc = form.save(commit=False)
        kyc.user = request.user
        kyc.status = 'pending'
        kyc.save()
        request.user.verification_status = 'pending'
        request.user.save(update_fields=['verification_status'])
        messages.success(request, 'Documents submitted. We will review within 24 hours.')
        return redirect('accounts:settings')

    return render(request, 'accounts/kyc_submit.html', {'form': form})
