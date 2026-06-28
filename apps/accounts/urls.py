from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

app_name = 'accounts'

urlpatterns = [
    # ── Auth ──────────────────────────────────────────
    path('signup/role/', views.signup_role, name='signup_role'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ── Password reset (Django built-in flow) ─────────
    path('password/forgot/', views.forgot_password, name='forgot_password'),
    path('password/reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='accounts/password_reset_confirm.html',
             success_url=reverse_lazy('accounts:password_reset_complete'),
         ),
         name='password_reset_confirm'),
    path('password/reset/done/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='accounts/password_reset_complete.html'
         ),
         name='password_reset_complete'),

    # ── Profile ───────────────────────────────────────
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('users/<str:username>/', views.public_profile, name='public_profile'),

    # ── Settings (progressive disclosure) ─────────────
    path('settings/', views.settings_overview, name='settings'),
    path('settings/security/', views.settings_security, name='settings_security'),
    path('settings/notifications/', views.settings_notifications, name='settings_notifications'),

    # ── KYC ───────────────────────────────────────────
    path('verify/', views.kyc_submit, name='kyc_submit'),
]
