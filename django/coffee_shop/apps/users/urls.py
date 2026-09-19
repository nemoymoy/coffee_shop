"""URLs for users app."""
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from coffee_shop.views import dashboard_view, profile_view
from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(
        next_page='catalog:catalog'), name='logout'),
    path('register/', views.register_view, name='register'),
    path(
        'personal-data-consent/',
        views.personal_data_consent_text_view,
        name='personal_data_consent_text',
    ),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('profile/', profile_view, name='profile'),

    # Email verification
    path(
        'verify-email/<uuid:token>/',
        views.verify_email_view,
        name='verify_email',
    ),
    path(
        'verification-pending/',
        TemplateView.as_view(template_name='users/email_verification_pending.html'),
        name='email_verification_pending',
    ),
    path(
        'verification-success/',
        TemplateView.as_view(template_name='users/email_verified.html'),
        name='email_verified',
    ),
    path(
        'verification-error/',
        TemplateView.as_view(template_name='users/email_verification_error.html'),
        name='email_verification_error',
    ),
    path(
        'resend-verification/',
        views.resend_verification_view,
        name='resend_verification',
    ),
]
