"""Admin for users app."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from coffee_shop.apps.users.models import PersonalDataConsent, UserEmailVerification


@admin.register(PersonalDataConsent)
class PersonalDataConsentAdmin(admin.ModelAdmin):
    list_display = ['user', 'version', 'consented_at', 'ip_address']
    list_filter = ['version', 'consented_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['consented_at', 'ip_address', 'user_agent', 'content_hash']


# Переопределяем стандартную модель User для Django Admin
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    ordering = ['-date_joined']


# Регистрация переопределённого UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserEmailVerification)
class UserEmailVerificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'token', 'is_used', 'is_expired', 'created_at']
    list_filter = ['is_used']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'expires_at', 'token']
