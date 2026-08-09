"""User forms for users app."""
from django.contrib.auth.models import User
from django.forms import ModelForm, TextInput, EmailInput


class UserUpdateForm(ModelForm):
    """Форма обновления профиля пользователя."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']
        widgets = {
            'first_name': TextInput(attrs={'class': 'form-control'}),
            'last_name': TextInput(attrs={'class': 'form-control'}),
            'username': TextInput(attrs={'class': 'form-control'}),
            'email': EmailInput(attrs={'class': 'form-control'}),
        }
