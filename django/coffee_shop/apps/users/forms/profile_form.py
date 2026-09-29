"""User profile form for additional user data."""
from django.forms import ModelForm, TextInput, DateInput, Select

from coffee_shop.apps.users.models import UserProfile


class UserProfileForm(ModelForm):
    """Форма обновления дополнительного профиля пользователя."""

    class Meta:
        model = UserProfile
        fields = ['phone', 'birth_date', 'gender']
        widgets = {
            'phone': TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+7 (___) ___-__-__',
            }),
            'birth_date': DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'gender': Select(attrs={
                'class': 'form-select',
            }),
        }
