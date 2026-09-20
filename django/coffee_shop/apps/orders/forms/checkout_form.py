"""Checkout form for orders."""
import re

from django import forms
from django.core.exceptions import ValidationError


class CheckoutForm(forms.Form):
    """Форма оформления заказа."""

    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Имя'
        })
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Фамилия'
        })
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+7 (999) 123-45-67'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'email@example.com'
        })
    )
    comment = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Комментарий к заказу'
        }),
        required=False
    )

    def clean_phone(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone', '')
        if not phone:
            return phone

        # Extract digits from phone
        digits = ''.join(c for c in phone if c.isdigit())

        # Handle Russian phone: 8 at start → replace with 7
        if digits.startswith('8') and len(digits) == 11:
            digits = '7' + digits[1:]

        # Validate: must be 11 digits starting with 7
        if not re.match(r'^7\d{10}$', digits):
            raise ValidationError(
                'Номер телефона должен содержать 11 цифр и '
                'начинаться с +7 (или 8 в начале)'
            )

        return phone
