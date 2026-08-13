"""Forms for news app."""
from django import forms

from ..models import News, Promotion


class NewsForm(forms.ModelForm):
    """Форма для создания/редактирования новости."""

    class Meta:
        model = News
        fields = ['title', 'slug', 'content', 'image', 'is_published', 'published_at']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Заголовок новости',
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'url-novosti',
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 10,
                'placeholder': 'Содержание новости',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
            }),
            'is_published': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'published_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
        }


class PromotionForm(forms.ModelForm):
    """Форма для создания/редактирования акции."""

    class Meta:
        model = Promotion
        fields = ['title', 'slug', 'description', 'image', 'is_active', 'start_date', 'end_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Заголовок акции',
            }),
            'slug': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'akciya-2024',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Описание акции',
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': 'form-control',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'start_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'end_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError('Дата окончания не может быть раньше даты начала.')

        return cleaned_data
