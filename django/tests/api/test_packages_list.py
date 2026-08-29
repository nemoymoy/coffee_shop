"""Tests for packages list API endpoint."""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from coffee_shop.apps.orders.models import Package

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestPackagesListEndpoint:
    """Тесты для endpoint получения списка тар."""

    def test_packages_list_returns_all_packages(self, client):
        """Packages list endpoint возвращает все тары."""
        user = User.objects.create_user(username='testuser', password='test123')
        client.force_login(user)

        response = client.get(reverse('orders:packages_list'))
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['packages']) == 5

    def test_packages_list_returns_correct_fields(self, client):
        """Packages list endpoint возвращает корректные поля."""
        user = User.objects.create_user(username='testuser2', password='test123')
        client.force_login(user)

        response = client.get(reverse('orders:packages_list'))
        data = response.json()
        
        package = data['packages'][0]
        assert 'weight_range' in package
        assert 'length' in package
        assert 'width' in package
        assert 'height' in package
        assert 'tare_weight' in package

    def test_packages_list_correct_weights(self, client):
        """Packages list endpoint возвращает корректные веса тар."""
        user = User.objects.create_user(username='testuser3', password='test123')
        client.force_login(user)

        response = client.get(reverse('orders:packages_list'))
        data = response.json()
        
        # Map by weight_range
        packages_by_range = {p['weight_range']: p for p in data['packages']}
        
        assert packages_by_range['light']['tare_weight'] == '0.023'
        assert packages_by_range['medium']['tare_weight'] == '0.050'
        assert packages_by_range['heavy']['tare_weight'] == '0.080'
        assert packages_by_range['xl']['tare_weight'] == '0.150'
        assert packages_by_range['xxl']['tare_weight'] == '0.300'

    def test_packages_list_unauthorized(self, client):
        """Packages list endpoint требует авторизации."""
        response = client.get(reverse('orders:packages_list'))
        
        # Должен быть 302 redirect на login
        assert response.status_code == 302
