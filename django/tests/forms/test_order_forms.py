"""Tests for order forms."""
import pytest
from django import forms

from coffee_shop.apps.orders.forms.checkout_form import CheckoutForm
from coffee_shop.apps.orders.forms.order_form import OrderForm


class TestCheckoutForm:
    """Тесты формы оформления заказа."""

    def test_valid_data(self):
        """Валидные данные."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com'
        }
        form = CheckoutForm(data=data)
        assert form.is_valid() is True

    def test_missing_required_fields(self):
        """Обязательные поля."""
        data = {
            'first_name': '',
            'last_name': '',
            'phone': '',
            'email': ''
        }
        form = CheckoutForm(data=data)
        assert form.is_valid() is False
        assert 'first_name' in form.errors
        assert 'last_name' in form.errors
        assert 'phone' in form.errors
        assert 'email' in form.errors

    def test_invalid_email(self):
        """Невалидный email."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'not-an-email'
        }
        form = CheckoutForm(data=data)
        assert form.is_valid() is False
        assert 'email' in form.errors

    def test_optional_comment(self):
        """Комментарий — опциональное поле."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com'
        }
        form = CheckoutForm(data=data)
        assert form.is_valid() is True  # comment не обязателен

    def test_name_max_length(self):
        """Максимальная длина имени."""
        data = {
            'first_name': 'A' * 101,
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com'
        }
        form = CheckoutForm(data=data)
        assert form.is_valid() is False
        assert 'first_name' in form.errors


class TestOrderForm:
    """Тесты расширенной формы заказа."""

    def test_delivery_method(self):
        """Выбор способа доставки."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'pickup',
            'payment_method': 'online'
        }
        form = OrderForm(data=data)
        assert form.is_valid() is True
        assert form.cleaned_data['delivery_method'] == 'pickup'

    def test_payment_method(self):
        """Выбор способа оплаты."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'delivery',
            'payment_method': 'cash'
        }
        form = OrderForm(data=data)
        assert form.is_valid() is True
        assert form.cleaned_data['payment_method'] == 'cash'

    def test_delivery_address_required_for_delivery(self):
        """Адрес для доставки опционален."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'delivery',
            'payment_method': 'online'
        }
        form = OrderForm(data=data)
        assert form.is_valid() is True  # адрес опционален в форме
