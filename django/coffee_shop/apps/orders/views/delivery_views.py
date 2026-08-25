"""Yandex Delivery views — Cargo API integration."""
import logging
import json
import hashlib
import requests as http_requests
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.core.cache import cache

from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def calculate_delivery_view(request):
    """
    Calculate delivery price and ETA via Cargo API.

    POST JSON:
    {
        "destination_coords": [49.35, 53.21],
        "destination_address": "ул. Примерная, д. 10",
        "pvz_id": "12345",
        "delivery_type": "pickup"
    }

    Returns JSON:
    {
        "success": true,
        "price": 299,
        "currency": "RUB",
        "mock": false
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({
            'success': False,
            'error': 'Некорректные данные',
        }, status=400)

    destination_coords = data.get('destination_coords')
    destination_address = data.get('destination_address', '')
    pvz_id = data.get('pvz_id')
    delivery_type = data.get('delivery_type', 'courier')

    # Parse coordinates from string "lon,lat" to array [lon, lat]
    if destination_coords and isinstance(destination_coords, str):
        parts = destination_coords.split(',')
        if len(parts) == 2:
            try:
                destination_coords = [float(parts[0].strip()), float(parts[1].strip())]
            except (ValueError, IndexError):
                return JsonResponse({
                    'success': False,
                    'error': 'Некорректный формат координат',
                }, status=400)

    # Fallback: if no coordinates but city/street/house provided, try to geocode
    city = data.get('city', '')
    street = data.get('street', '')
    house = data.get('house', '')
    apartment = data.get('apartment', '')

    if not destination_coords and city and street and house:
        # Try geocoding (cached for 5 min)
        cache_key = f'geocode_{city}_{street}_{house}_{apartment}'
        cached_coords = cache.get(cache_key)
        if cached_coords:
            destination_coords = cached_coords['coords']
            destination_address = cached_coords['address']
        else:
            geocoder_api_key = getattr(settings, 'YANDEX_GEOCODER_API_KEY', '')
            if geocoder_api_key:
                try:
                    geocode_query = f'{city} {street} {house}'
                    if apartment:
                        geocode_query += f' {apartment}'

                    geocode_params = {
                        'apikey': geocoder_api_key,
                        'geocode': geocode_query,
                        'format': 'json',
                        'lang': 'ru_RU',
                        'results': '1',
                    }

                    geocode_response = http_requests.get(
                        'https://geocode-maps.yandex.ru/1.x/',
                        params=geocode_params,
                        timeout=5,
                    )

                    if geocode_response.status_code == 200:
                        geo_data = geocode_response.json()
                        features = geo_data.get('response', {}).get('GeoObjectCollection', {}).get('featureMember', [])
                        if features:
                            point = features[0].get('GeoObject', {}).get('Point', {})
                            if point and 'pos' in point:
                                coords = point['pos'].split()
                                destination_coords = [float(coords[0]), float(coords[1])]
                                destination_address = features[0].get('GeoObject', {}).get('metaDataProperty', {}).get('GeocoderMetaData', {}).get('text', geocode_query)
                                cache.set(cache_key, {
                                    'coords': destination_coords,
                                    'address': destination_address,
                                }, 300)
                except http_requests.exceptions.HTTPError as e:
                    if e.response and e.response.status_code == 429:
                        logger.warning('Geocoding rate limited')
                except Exception as e:
                    logger.warning('Geocoding failed: %s', e)

    if not destination_coords:
        return JsonResponse({
            'success': False,
            'error': 'Не удалось определить координаты доставки',
        }, status=400)

    service = YandexDeliveryService()

    if not service.is_configured():
        logger.warning('calculate_delivery: Yandex Delivery не настроен (нет токена)')
        return JsonResponse({
            'success': False,
            'error': 'Яндекс Доставка не настроена. Обратитесь к администратору.',
        }, status=200)

    # Build items payload
    items = [
        {
            'quantity': 1,
            'weight': 0.5,
            'size': {'length': 0.3, 'width': 0.2, 'height': 0.1},
        }
    ]

    result = service.calculate_price(
        items=items,
        destination_coords=destination_coords,
        destination_address=destination_address,
        delivery_type=delivery_type,
    )

    if result.get('success'):
        response_data = {
            'success': True,
            'price': result.get('price', 0),
            'currency': 'RUB',
            'delivery_days': result.get('delivery_days'),
            'eta': result.get('eta'),
        }
        return JsonResponse(response_data)
    else:
        logger.warning('Ошибка расчёта доставки (возврат ошибки клиенту): %s', result.get('error'))
        return JsonResponse({
            'success': False,
            'error': result.get('error', 'Не удалось рассчитать стоимость доставки'),
        }, status=200)


@login_required
def pvz_locations_view(request):
    """
    Return PVZ/terminal list (placeholder for future API integration).
    Currently returns mock data for frontend widget.

    GET params:
    - type: 'pvz' or 'postomat'
    - city: city name
    """
    # For now, return empty list - the widget handles PVZ selection via Yandex
    return JsonResponse({
        'success': True,
        'points': [],
        'mock': True,
    })


@csrf_exempt
@require_POST
def geocode_address_view(request):
    """
    Geocode addresses via Yandex Geocoder API.

    POST JSON:
    {
        "query": "Самара ул Революционная 3 кв 5"
    }

    Returns JSON:
    {
        "success": true,
        "results": ["адрес1", "адрес2", ...],
        "features": [...]}
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({
            'success': False,
            'error': 'Некорректные данные',
        }, status=400)

    query = data.get('query', '').strip()
    if not query:
        return JsonResponse({
            'success': False,
            'error': 'Запрос пустой',
        }, status=400)

    api_key = getattr(settings, 'YANDEX_GEOCODER_API_KEY', '') or \
              getattr(settings, 'YANDEX_MAPS_API_KEY', '')

    if not api_key:
        return JsonResponse({
            'success': False,
            'error': 'API ключ не настроен',
        }, status=500)

    # Cache geocoding results for 5 minutes (uses hash to avoid key issues)
    cache_key = f'geocode_{hashlib.md5(query.encode()).hexdigest()}'
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    try:
        url = 'https://geocode-maps.yandex.ru/1.x/'
        params = {
            'apikey': api_key,
            'geocode': query,
            'format': 'json',
            'lang': 'ru_RU',
            'results': '10',
        }

        response = http_requests.get(url, params=params, timeout=5)

        if response.status_code == 429:
            logger.warning('Geocoder rate limited for query: %s', query)
            return JsonResponse({
                'success': True,
                'results': [],
                'features': [],
                'rate_limited': True,
            })

        if response.status_code != 200:
            logger.warning('Geocoder API error: %s', response.status_code)
            return JsonResponse({
                'success': True,
                'results': [],
                'features': [],
                'api_error': True,
            })

        geocoder_data = response.json()

        results = []
        features = []

        response_obj = geocoder_data.get('response', {})
        geo_object_collection = response_obj.get('GeoObjectCollection', {})
        feature_members = geo_object_collection.get('featureMember', [])

        for feature in feature_members:
            geo_object = feature.get('GeoObject', {})

            meta = geo_object.get('metaDataProperty', {}).get('GeocoderMetaData', {})
            text = meta.get('text', '')

            point = geo_object.get('Point')
            coords = None
            if point:
                pos = point.get('pos', '')
                if pos:
                    coords = pos.split(' ')

            if text:
                results.append(text)
                features.append({
                    'text': text,
                    'coords': coords,
                })

        result_data = {
            'success': True,
            'results': results,
            'features': features,
        }
        # Cache for 5 minutes
        cache.set(cache_key, result_data, 300)

        return JsonResponse(result_data)

    except http_requests.exceptions.Timeout:
        return JsonResponse({
            'success': False,
            'error': 'Таймаут запроса',
        }, status=504)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


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
    # The payload structure depends on Yandex's webhook format
    # Common fields: point_id, point_type, coordinates, address, etc.
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
    # that calls the callback function with the selected point data
    # The format: <script>window.YandexDeliveryCallback({...})</script>
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
