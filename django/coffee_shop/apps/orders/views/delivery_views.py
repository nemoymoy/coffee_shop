"""Yandex Delivery views — Cargo API integration."""
import json
import logging
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService
from coffee_shop.apps.orders.services.geocoder_service import YandexGeocoderService
from coffee_shop.apps.orders.models import Package

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def calculate_delivery_view(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Некорректные данные'}, status=400)

    destination_coords = data.get('destination_coords')
    destination_address = data.get('destination_address', '')
    pvz_id = data.get('pvz_id')
    delivery_type = data.get('delivery_type', 'courier')

    # Parse coordinates from string "lon,lat" to list [lon, lat]
    if isinstance(destination_coords, str):
        geocoder = YandexGeocoderService()
        parsed = geocoder.parse_coords(destination_coords)
        if parsed is None:
            return JsonResponse({'success': False, 'error': 'Некорректный формат координат'}, status=400)
        destination_coords = parsed

    if not destination_coords:
        return JsonResponse({'success': False, 'error': 'Не удалось определить координаты доставки'}, status=400)

    service = YandexDeliveryService()

    if not service.is_configured():
        logger.warning('calculate_delivery: Yandex Delivery not configured')
        return JsonResponse({'success': False, 'error': 'Яндекс Доставка не настроена'}, status=200)

    try:
        # Получаем товары из POST (от фронтенда) или из session (резерв)
        data = json.loads(request.body)
        cart_items_from_frontend = data.get('cart_items', [])
        session_cart = request.session.get('cart', {})

        if not cart_items_from_frontend and not session_cart:
            return JsonResponse({'success': False, 'error': 'Корзина пуста'}, status=200)

        items_payload = []
        if cart_items_from_frontend:
            # Используем товары из фронтенда
            # Сначала суммируем вес всех товаров
            total_weight_grams = 0
            total_quantity = 0
            for item in cart_items_from_frontend:
                try:
                    weight_grams = int(item.get('weight', 0))
                    quantity = int(item.get('quantity', 1))
                    total_weight_grams += weight_grams * quantity
                    total_quantity += quantity
                except (ValueError, TypeError):
                    continue

            # Теперь выбираем ОДНУ тару для суммарного веса
            if total_weight_grams > 0:
                package = Package.for_weight(total_weight_grams)
                total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)

                items_payload.append({
                    'quantity': total_quantity,
                    'weight': round(total_weight_kg, 3),
                    'size': {
                        'length': float(package.length),
                        'width': float(package.width),
                        'height': float(package.height),
                    },
                    'title': 'Товар',
                })
        else:
            # Резерв: берем из session
            total_weight_grams = 0
            total_quantity = 0
            session_items = []
            for key, value in session_cart.items():
                try:
                    from coffee_shop.apps.catalog.models import Product
                    product = Product.objects.get(pk=value['product_id'])
                    weight_grams = int(value.get('weight', 0))
                    quantity = int(value.get('quantity', 1))
                    total_weight_grams += weight_grams * quantity
                    total_quantity += quantity
                    session_items.append({'product': product, 'weight_grams': weight_grams, 'quantity': quantity})
                except (Product.DoesNotExist, ValueError):
                    continue

            # Теперь выбираем ОДНУ тару для суммарного веса
            if total_weight_grams > 0:
                package = Package.for_weight(total_weight_grams)
                total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)

                items_payload.append({
                    'quantity': total_quantity,
                    'weight': round(total_weight_kg, 3),
                    'size': {
                        'length': float(package.length),
                        'width': float(package.width),
                        'height': float(package.height),
                    },
                    'title': session_items[0]['product'].name if session_items else 'Товар',
                })

        if not items_payload:
            return JsonResponse({'success': False, 'error': 'В корзине нет товаров'}, status=200)

        result = service.calculate_price(
            items=items_payload,
            destination_coords=destination_coords,
            destination_address=destination_address,
            delivery_type=delivery_type,
        )

        if result.get('success'):
            return JsonResponse({
                'success': True,
                'price': result.get('price', 0),
                'currency': 'RUB',
                'delivery_days': result.get('delivery_days'),
                'eta': result.get('eta'),
            })
        else:
            return JsonResponse({'success': False, 'error': result.get('error', 'Ошибка расчёта')}, status=200)
    except Exception as e:
        logger.exception('calculate_delivery unexpected error')
        return JsonResponse({'success': False, 'error': 'Внутренняя ошибка сервера'}, status=500)


@login_required
def postamats_list_view(request):
    """
    Return postamat (terminal) list from Yandex Delivery API.

    GET params:
        radius_km: Geo-filter radius in km (default: 50)
        max_results: Max points to return (default: 500)

    GET /checkout/postamats/?radius_km=30&max_results=100

    Returns JSON:
    {
        "success": true,
        "points": [
            {
                "id": "12345",
                "name": "Постомат Яндекс",
                "address": "Самара, ул. ...",
                "latitude": 53.21,
                "longitude": 50.16,
                "operator_id": "market_l4g",
                "type": "terminal",
                "work_schedule": {...},
                "distance_km": 2.5
            }
        ],
        "count": 5
    }
    """
    service = YandexDeliveryService()

    # Parse query parameters
    try:
        radius_km = float(request.GET.get('radius_km', 50))
        max_results = int(request.GET.get('max_results', 500))
    except (ValueError, TypeError):
        return JsonResponse({
            'success': False,
            'points': [],
            'count': 0,
            'error': 'Некорректные параметры запроса',
        }, status=400)

    # Clamp values
    radius_km = max(1, min(radius_km, 200))
    max_results = max(1, min(max_results, 1000))

    result = service.get_postamats(
        operator_ids=['market_l4g'],
        center_lat=getattr(settings, 'YANDEX_SHOP_LAT', 53.216940239129094),
        center_lon=getattr(settings, 'YANDEX_SHOP_LON', 50.162688008923745),
        radius_km=radius_km,
        max_results=max_results,
    )

    if result.get('success'):
        return JsonResponse({
            'success': True,
            'points': result.get('points', []),
            'count': result.get('count', 0),
            'message': result.get('message'),
        })
    else:
        logger.warning('postamats_list: %s', result.get('error'))
        return JsonResponse({
            'success': False,
            'points': [],
            'count': 0,
            'error': result.get('error', 'Не удалось получить постоматы'),
        }, status=200)


@login_required
def packages_list_view(request):
    """
    Return all Package records for frontend tare weight lookup.

    GET /checkout/packages/
    Returns JSON:
    {
        "success": true,
        "packages": [
            {
                "weight_range": "medium",
                "length": 0.200,
                "width": 0.120,
                "height": 0.120,
                "tare_weight": 0.050
            },
            ...
        ]
    }
    """
    packages = list(Package.objects.values(
        'weight_range', 'length', 'width', 'height', 'tare_weight'
    ))
    return JsonResponse({
        'success': True,
        'packages': packages,
    })


@login_required
def pvz_locations_view(request):
    """
    Return PVZ list from Yandex Delivery API.

    GET params:
    - type: 'pvz' or 'postomat' (defaults to 'pvz')

    Returns JSON:
    {
        "success": true,
        "points": [
            {
                "id": "...",
                "name": "...",
                "address": "...",
                "latitude": 53.2,
                "longitude": 50.1,
                "operator_id": "market_l4g",
                "type": "pickup_point",
                "work_schedule": {...}
            }
        ],
        "count": 42
    }
    """
    delivery_type = request.GET.get('type', 'pvz')
    # Фильтруем на бэкенде: для ПВЗ — только pickup_point, для постоматов — отдельный endpoint

    service = YandexDeliveryService()
    result = service.get_pickup_points(
        operator_ids=['market_l4g'],
        point_type='pickup_point',
        center_lat=getattr(settings, 'YANDEX_SHOP_LAT', 53.216940239129094),
        center_lon=getattr(settings, 'YANDEX_SHOP_LON', 50.162688008923745),
        radius_km=50,
        max_results=500,
    )

    # Фильтруем точки по типу
    points = result.get('points', [])
    if delivery_type == 'pvz':
        points = [p for p in points if p.get('type') == 'pickup_point']

    if result.get('success'):
        return JsonResponse({
            'success': True,
            'points': points,
            'count': len(points),
        })
    else:
        logger.warning('pvz_locations: %s', result.get('error'))
        return JsonResponse({
            'success': False,
            'points': [],
            'count': 0,
            'error': result.get('error', 'Не удалось получить точки выдачи'),
        }, status=200)


@csrf_exempt
@require_POST
def geocode_address_view(request):
    """
    Geocode addresses via Yandex Geocoder API (delegated to YandexGeocoderService).

    POST JSON:
    {
        "query": "Самара ул Революционная 3 кв 5"
    }

    Returns JSON:
    {
        "success": true,
        "results": ["адрес1", "адрес2", ...],
        "features": [{"text": "...", "coords": [lon, lat]}, ...],
        "rate_limited": false,
        "api_error": false
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'},
            status=400
        )

    query = data.get('query', '').strip()
    if not query:
        return JsonResponse(
            {'success': False, 'error': 'Запрос пустой'},
            status=400
        )

    geocoder = YandexGeocoderService()
    result = geocoder.geocode(query, results=10)

    if 'error' in result:
        return JsonResponse(result, status=400)

    return JsonResponse({
        'success': result['success'],
        'results': result.get('results', []),
        'features': result.get('features', []),
        'rate_limited': result.get('rate_limited', False),
        'api_error': result.get('api_error', False),
    })


@login_required
def packages_list_view(request):
    """
    Return all Package records for frontend tare weight lookup.

    GET /checkout/packages/
    Returns JSON:
    {
        "success": true,
        "packages": [
            {
                "weight_range": "medium",
                "length": 0.200,
                "width": 0.120,
                "height": 0.120,
                "tare_weight": 0.050
            },
            ...
        ]
    }
    """
    packages = list(Package.objects.values(
        'weight_range', 'length', 'width', 'height', 'tare_weight'
    ))
    return JsonResponse({
        'success': True,
        'packages': packages,
    })


@csrf_exempt
@require_POST
def yandex_delivery_webhook(request):
    """
    Webhook endpoint for Yandex Delivery widget.
    Called by Yandex when user selects a PVZ/terminal.
    Sends back a simple HTML page that calls window.YandexDeliveryCallback.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        # Yandex expects HTML response, not JSON
        return HttpResponse(
            '<html><body>OK</body></html>',
            content_type='text/html',
            status=200,
        )

    # Extract point data from Yandex payload
    point_id = data.get('id') or data.get('point_id', '')
    point_type = data.get('type', '')
    point_name = data.get('name', '') or data.get('title', '')
    point_address = data.get('address', '') or data.get('full_address', '')

    # Yandex might send nested payload
    payload = data.get('payload', data)
    if not point_id:
        point_id = payload.get('id') or payload.get('point_id', '')
    if not point_address:
        point_address = payload.get('address', '') or payload.get('full_address', '')
    if not point_name:
        point_name = payload.get('name', '') or payload.get('title', '')

    logger.info(
        'Yandex Delivery webhook received: id=%s type=%s address=%s',
        point_id, point_type, point_address,
    )

    # Yandex Delivery widget expects an HTML response with JavaScript
    callback_data = json.dumps({
        'pointId': point_id,
        'pointType': point_type,
        'name': point_name,
        'address': point_address,
    }, ensure_ascii=False)

    html = (
        f'<script>window.YandexDeliveryCallback({callback_data});</script>'
        f'<html><body>Point selected: {point_name}</body></html>'
    )
    return HttpResponse(html, content_type='text/html')


@user_passes_test(lambda u: u.is_staff)
def yandex_delivery_status_view(request):
    """
    Integration status page for Yandex Delivery.
    Shows API configuration status.
    """
    service = YandexDeliveryService()

    status_info = {
        'configured': service.is_configured(),
        'shop_address': service.shop_address,
        'shop_coordinates': [service.shop_lon, service.shop_lat],
    }

    return JsonResponse(status_info)
