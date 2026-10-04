"""Product filter form."""
from django import forms

from coffee_shop.apps.catalog.models import Product


class ProductForm(forms.Form):
    """Фильтры каталога товаров."""

    category = forms.CharField(required=False, widget=forms.HiddenInput())
    min_price = forms.DecimalField(required=False, label='Мин. цена', max_digits=10, decimal_places=2)
    max_price = forms.DecimalField(required=False, label='Макс. цена', max_digits=10, decimal_places=2)
    roast_level = forms.ChoiceField(required=False, label='Обжарка')
    processing_method = forms.ChoiceField(required=False, label='Обработка')
    min_sca = forms.IntegerField(required=False, label='Мин. SCA')

    def __init__(self, *args, **kwargs):
        product_types = kwargs.pop('product_types', [])
        categories = kwargs.pop('categories', [])
        super().__init__(*args, **kwargs)
        from ..models import Product
        self.fields['roast_level'].choices = Product.ROAST_CHOICES
        self.fields['processing_method'].choices = [
            ('natural', 'Натуральная'),
            ('washed', 'Мытая'),
            ('honey', 'Медовая'),
            ('anaerobic', 'Анаэробная'),
            ('other', 'Другая'),
        ]


class ProductAdminForm(forms.ModelForm):
    """Кастомная форма для Product с валидацией по stock_unit."""

    class Meta:
        model = Product
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        stock_unit = cleaned_data.get('stock_unit')
        price_per_50g = cleaned_data.get('price_per_50g')
        base_price = cleaned_data.get('base_price')

        if stock_unit == Product.STOCK_UNIT_GRAM and not price_per_50g:
            raise forms.ValidationError({
                'price_per_50g': 'Обязательное поле для товаров в граммах (кофе)'
            })

        if stock_unit == Product.STOCK_UNIT_UNIT:
            cleaned_data['price_per_50g'] = None

        return cleaned_data
