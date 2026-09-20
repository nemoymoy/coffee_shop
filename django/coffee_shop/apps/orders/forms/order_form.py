"""Order form."""
import re

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from .checkout_form import CheckoutForm


class OrderForm(CheckoutForm):
    """Расширенная форма заказа с полями доставки и промокодом."""

    promo_code = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Промокод (необязательно)'
        }),
        label='Промокод'
    )
    delivery_method = forms.ChoiceField(
        choices=[
            ('pickup', 'Самовывоз'),
            ('delivery', 'Доставка'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'btn-check'}),
        label='Способ получения'
    )
    delivery_type = forms.ChoiceField(
        choices=[
            ('courier', 'Курьер'),
            ('pickup', 'ПВЗ'),
            ('postamat', 'Постомат'),
        ],
        widget=forms.HiddenInput(),
        required=False,
    )
    pvz_id = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    destination_coords = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    payment_method = forms.ChoiceField(
        choices=[
            ('online', 'Онлайн'),
            ('cash', 'При получении'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'btn-check'}),
        label='Способ оплаты'
    )
    delivery_address = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Адрес доставки'
        }),
        required=False
    )
    delivery_cost = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    delivery_date = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    delivery_time = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    yandex_request_id = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    def clean_delivery_cost(self):
        """Clean delivery_cost: convert comma to dot for DecimalField."""
        value = self.cleaned_data.get('delivery_cost', '')
        if not value:
            return Decimal('0')
        # Convert comma to dot (JS formats prices as '350,00' in Russian locale)
        if isinstance(value, str):
            value = value.replace(',', '.')
        return value

    def clean(self):
        cleaned_data = super().clean()
        delivery_method = cleaned_data.get('delivery_method')
        delivery_address = cleaned_data.get('delivery_address')
        phone = cleaned_data.get('phone', '')

        # Validate phone format
        if phone:
            digits = ''.join(c for c in phone if c.isdigit())
            # Handle Russian phone: 8 at start → replace with 7
            if digits.startswith('8') and len(digits) == 11:
                digits = '7' + digits[1:]
            if not re.match(r'^7\d{10}$', digits):
                self.add_error('phone', 'Номер телефона должен содержать 11 цифр и начинаться с +7')

        if delivery_method == 'delivery':
            # Для курьера нужен адрес
            if not delivery_address:
                self.add_error('delivery_address', 'Необходимо указать адрес доставки')

        return cleaned_data
