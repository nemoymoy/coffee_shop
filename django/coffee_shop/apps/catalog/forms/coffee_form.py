from django import forms
from ..services.coffee_service import CoffeeService


class CoffeeForm(forms.Form):
    """Форма выбора параметров кофе."""

    WEIGHT_CHOICES = []  # Генерируется динамически

    weight = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 50,
            'step': 50,
            'placeholder': 'Выберите вес (кратен 50 г)'
        })
    )
    coffee_form = forms.ChoiceField(
        choices=[
            ('beans', 'В зёрнах'),
            ('ground', 'Молотый'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'btn-check'}),
        label='Форма кофе'
    )
    brewing_method = forms.ChoiceField(
        choices=[
            ('turka', 'Турка (джезва)'),
            ('espresso', 'Эспрессо-машина'),
            ('geyser', 'Гейзер (мокка)'),
            ('pourover', 'Пуровер (воронка)'),
            ('siphon', 'Сифон (габет)'),
            ('aeropress', 'Аэропресс'),
            ('chemex', 'Кемекс'),
            ('french_press', 'Френч-пресс'),
            ('capping', 'Помол на каппинг'),
            ('filter_machine', 'Фильтр-машина'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label='Способ заваривания'
    )

    def __init__(self, product, *args, **kwargs):
        super().__init__(*args, **kwargs)
        available_weights = CoffeeService.get_available_weights(product)
        if available_weights:
            self.WEIGHT_CHOICES = [(w, f'{w} г') for w in available_weights]
            self.fields['weight'].choices = self.WEIGHT_CHOICES
            self.fields['weight'].widget.attrs['max'] = max(available_weights)
        else:
            self.fields['weight'].choices = []
            self.fields['weight'].widget.attrs['disabled'] = 'disabled'

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        if not weight:
            raise forms.ValidationError('Укажите вес')
        if weight % 50 != 0:
            raise forms.ValidationError('Вес должен быть кратен 50 г')
        return weight

    def clean(self):
        cleaned_data = super().clean()
        coffee_form = cleaned_data.get('coffee_form')
        brewing_method = cleaned_data.get('brewing_method')

        is_valid, error = CoffeeService.validate_brewing_method(
            coffee_form, brewing_method
        )
        if not is_valid:
            raise forms.ValidationError(error)

        return cleaned_data
