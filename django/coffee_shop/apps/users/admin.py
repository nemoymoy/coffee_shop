"""Admin configuration for users app."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from coffee_shop.apps.users.models import (
    UserProfile, PersonalDataConsent, UserEmailVerification, DeliveryAddress,
)


class UserProfileInline(admin.StackedInline):
    """Inline-редактирование профиля пользователя."""
    model = UserProfile
    can_delete = False
    verbose_name = 'Профиль'
    verbose_name_plural = 'Профиль пользователя'
    fields = ('phone', 'birth_date', 'gender', 'email_verified_at', 'is_email_verified')
    readonly_fields = ('email_verified_at', 'is_email_verified')


class DeliveryAddressInline(admin.TabularInline):
    """Inline-редактирование адресов доставки."""
    model = DeliveryAddress
    extra = 0
    fields = ('label', 'full_address', 'apartment', 'coordinates', 'is_default')
    readonly_fields = ('coordinates',)
    can_delete = True
    verbose_name = 'Адрес доставки'
    verbose_name_plural = 'Адреса доставки'

    def has_add_permission(self, request, obj=None):
        """Запрещаем добавление адресов из карточки пользователя."""
        return False


class DeliveryAddressAdmin(admin.ModelAdmin):
    """Админ-панель для адресов доставки."""
    list_display = ('user', 'label', 'full_address', 'apartment', 'is_default', 'created_at')
    list_filter = ('is_default', 'user', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'label', 'full_address')
    readonly_fields = ('user', 'full_address', 'coordinates', 'created_at', 'updated_at')
    fieldsets = (
        ('Информация', {
            'fields': ('user', 'label', 'full_address', 'apartment')
        }),
        ('Координаты', {
            'fields': ('coordinates',),
            'classes': ('collapse',),
        }),
        ('Настройки', {
            'fields': ('is_default',),
        }),
        ('Время', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    actions = ['set_default', 'unset_default']

    def set_default(self, request, queryset):
        """Установить выбранные адреса как дефолтные."""
        count = 0
        for addr in queryset:
            addr.is_default = True
            addr.save()
            count += 1
        self.message_user(request, f'Адреса ({count}) установлены как дефолтные')
    set_default.short_description = 'Установить как "По умолчанию"'

    def unset_default(self, request, queryset):
        """Снять флаг дефолтного адреса."""
        count = queryset.update(is_default=False)
        self.message_user(request, f'Снято "По умолчанию" с {count} адресов')
    unset_default.short_description = 'Снять "По умолчанию"'


class UserEmailVerificationAdmin(admin.ModelAdmin):
    """Админ-панель для токенов подтверждения email.

    Токены удаляются после подтверждения — здесь видны только активные.
    Для проверки статуса верификации смотрите UserProfileInline в карточке пользователя.
    """
    list_display = ('user', 'created_at', 'expires_at', 'is_valid')
    list_filter = ('created_at', 'expires_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'token', 'created_at', 'expires_at')
    fieldsets = (
        ('Пользователь', {
            'fields': ('user',),
        }),
        ('Токен', {
            'fields': ('token',),
            'description': 'Токен удаляется после подтверждения email.',
        }),
        ('Время', {
            'fields': ('created_at', 'expires_at'),
            'classes': ('collapse',),
        }),
    )

    def has_add_permission(self, request):
        return False


# Re-register User with custom admin
class CustomUserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, DeliveryAddressInline)


# Unregister default User admin and re-register
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
admin.site.register(DeliveryAddress, DeliveryAddressAdmin)
admin.site.register(PersonalDataConsent)
admin.site.register(UserEmailVerification, UserEmailVerificationAdmin)
