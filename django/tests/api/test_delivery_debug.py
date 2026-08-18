"""Debug test to understand mock behavior."""
import pytest
from unittest.mock import patch, MagicMock, call
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_debug_mock_path(client):
    """Debug: check if mock is correctly applied."""
    from coffee_shop.apps.orders.views import delivery_views
    
    print(f"\nBEFORE PATCH:")
    print(f"  delivery_views.YandexDeliveryService = {delivery_views.YandexDeliveryService}")
    
    with patch(
        'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
    ) as MockService:
        print(f"\nINSIDE PATCH:")
        print(f"  delivery_views.YandexDeliveryService = {delivery_views.YandexDeliveryService}")
        print(f"  MockService = {MockService}")
        print(f"  Same? {delivery_views.YandexDeliveryService is MockService}")
        
        # Try to call the class
        instance = MockService()
        print(f"  MockService() = {instance}")
        print(f"  MockService.return_value = {MockService.return_value}")
        
        # Simulate what view does
        service = delivery_views.YandexDeliveryService('test-token')
        print(f"  YandexDeliveryService('test-token') = {service}")
        print(f"  Is it MockService.return_value? {service is MockService.return_value}")
        
        result = service.calculate_price({'city': 'moscow'})
        print(f"  service.calculate_price() = {result}")
    
    print(f"\nAFTER PATCH:")
    print(f"  delivery_views.YandexDeliveryService = {delivery_views.YandexDeliveryService}")


def test_debug_calculate_delivery(client):
    """Debug: check what happens during actual request."""
    user = User.objects.create_user(
        username='testuser', email='test@example.com', password='test123'
    )
    client.force_login(user)
    client.session['yandex_delivery_access_token'] = 'ya2-test-token'
    client.session.save()
    
    payload = {
        'city': 'moscow',
        'street': 'ул. Тестовая',
        'house': '1',
        'apartment': '10',
    }
    
    mock_instance = MagicMock()
    mock_instance.calculate_price.return_value = {
        'success': True,
        'price': 350,
        'eta': '40-60 мин',
    }
    
    with patch(
        'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
    ) as MockService:
        MockService.return_value = mock_instance
        
        # Debug: check what the view's class is right now
        from coffee_shop.apps.orders.views import delivery_views
        print(f"\nIn mock context:")
        print(f"  delivery_views.YandexDeliveryService = {delivery_views.YandexDeliveryService}")
        print(f"  MockService = {MockService}")
        print(f"  Are they the same? {delivery_views.YandexDeliveryService is MockService}")
        
        # Make request
        response = client.post(
            reverse('orders:calculate_delivery'),
            data=payload,
            content_type='application/json',
        )
        
        print(f"\nResponse: {response.status_code}")
        print(f"Response data: {response.json()}")
        print(f"MockService.call_args = {MockService.call_args}")
        print(f"mock_instance.calculate_price.call_args = {mock_instance.calculate_price.call_args}")
