"""Debug: check session access_token during request."""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_debug_access_token_in_view(client):
    """Check if access_token is present in session during request."""
    user = User.objects.create_user(
        username='testuser', email='test@example.com', password='test123'
    )
    client.force_login(user)
    client.session['yandex_delivery_access_token'] = 'ya2-test-token'
    client.session.save()
    
    # Verify session data was saved
    print(f"\nAfter save, session key exists: {'yandex_delivery_access_token' in client.session}")
    
    payload = {
        'city': 'moscow',
        'street': 'ул. Тестовая',
        'house': '1',
        'apartment': '10',
    }
    
    # Patch calculate_price to see if it's ever called
    with patch(
        'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService.calculate_price'
    ) as mock_calculate:
        mock_calculate.return_value = {
            'success': True,
            'price': 350,
            'eta': '40-60 мин',
        }
        
        response = client.post(
            reverse('orders:calculate_delivery'),
            data=payload,
            content_type='application/json',
        )
        
        print(f"\nResponse: {response.status_code}")
        print(f"Response data: {response.json()}")
        print(f"mock_calculate.call_count: {mock_calculate.call_count}")
        print(f"mock_calculate.call_args: {mock_calculate.call_args}")
