"""Order form."""
from django import forms
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
