"""Admin for users app."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User


# Переопределяем стандартную модель User для Django Admin
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    ordering = ['-date_joined']


# Регистрация переопределённого UserAdmin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
