"""Form for delivery address creation and editing."""
from django.forms import ModelForm, TextInput, Textarea

from coffee_shop.apps.users.models import DeliveryAddress


class DeliveryAddressForm(ModelForm):
    """Форма создания/редактирования адреса доставки."""

    class Meta:
        model = DeliveryAddress
        fields = ['label', 'full_address', 'apartment']
        widgets = {
            'label': TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Дом, Офис, Дача',
            }),
            'full_address': Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Город, улица, дом (автокомплит подставит адрес)',
                'readonly': True,
            }),
            'apartment': TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'кв. / оф.',
            }),
        }
