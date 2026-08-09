"""Product filter form."""
from django import forms


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
