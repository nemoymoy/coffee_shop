"""API views for delivery locations."""
from django.views.decorators.http import require_GET
from django.views.decorators.cache import cache_page
from django.http import JsonResponse
from django.conf import settings

from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService


@require_GET
@cache_page(60 * 60)  # Кэшируем на 1 час
def delivery_locations_api(request):
    """
    API endpoint для получения списка точек Яндекс Доставки.

    GET params:
    - type: тип точки - 'terminal' (ПВЗ), 'self_pickup', 'warehouse'
            (по умолчанию 'terminal')
    - geo_id: идентификатор города (по умолчанию из настроек)

    Returns JSON:
    {
        "success": true,
        "points": [
            {
                "platform_station_id": "123456789",
                "name": "ПВЗ Москва, ул. Примерная, 1",
                "type": "terminal",
                "address": "г. Москва, ул. Примерная, д. 1"
            }
        ],
        "mock": false
    }
    """
    point_type = request.GET.get('type', 'terminal')
    geo_id = request.GET.get('geo_id', None)

    service = YandexDeliveryService()
    result = service.get_locations(geo_id=geo_id, point_type=point_type)

    if result.get('success'):
        return JsonResponse({
            'success': True,
            'points': result.get('points', []),
            'mock': result.get('mock', False),
        })
    else:
        return JsonResponse({
            'success': False,
            'points': [],
            'error': result.get('error', 'Ошибка получения точек'),
        }, status=500)
