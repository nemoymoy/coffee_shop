"""Yandex Delivery views — Express + Other Day API integration.

Thin controllers that delegate to DeliveryPriceCalculator service.
"""
import functools
import json
import logging
import time

from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService
from coffee_shop.apps.orders.services.delivery_price_calculator import (
    DeliveryPriceCalculator,
)
from coffee_shop.apps.orders.services.geocoder_service import YandexGeocoderService
from coffee_shop.apps.orders.models import Order, Package

logger = logging.getLogger(__name__)


def _json_login_required(view_func):
    """Decorator that returns JSON 403 for AJAX requests when user is not authenticated.

    For non-AJAX requests, redirects to LOGIN_URL as normal @login_required does.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            if (
                request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or request.content_type == 'application/json'
            ):
                return JsonResponse({'error': 'login_required'}, status=403)
            return redirect(settings.LOGIN_URL)
        return view_func(request, *args, **kwargs)
    return wrapper


def _parse_coords(coords):
    """Parse destination_coords from string or list to [lon, lat].

    Returns:
        [float, float] or None on failure.
    """
    if isinstance(coords, str):
        geocoder = YandexGeocoderService()
        parsed = geocoder.parse_coords(coords)
        if parsed is None:
            return None
        return parsed
    elif isinstance(coords, list):
        try:
            return [float(coords[0]), float(coords[1])]
        except (ValueError, IndexError):
            return None
    return None


def _determine_api_type(delivery_type):
    """Determine which API to use based on delivery type."""
    if delivery_type in ('pickup', 'postamat'):
        return 'other_day'
    return 'express'


@csrf_exempt
@require_POST
@_json_login_required
def create_express_delivery_view(request):
    """Create Express delivery order in Yandex (price estimation).

    POST JSON:
    {
        "destination_coords": "[lon,lat]",
        "destination_address": "...",
        "delivery_type": "courier",
        "cart_items": [...]
    }

    Returns:
    {
        "success": true,
        "claim_id": "...",
        "price": "450.18",
        "currency": "RUB",
        "expires_in_seconds": 600
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'}, status=400
        )

    destination_coords = _parse_coords(data.get('destination_coords'))
    if not destination_coords:
        return JsonResponse(
            {'success': False, 'error': 'Не удалось определить координаты'},
            status=400,
        )

    if data.get('delivery_type', 'courier') != 'courier':
        return JsonResponse(
            {'success': False, 'error': 'Только курьерская доставка'},
            status=400,
        )

    calculator = DeliveryPriceCalculator()
    items_payload = calculator.build_items_from_cart(
        data.get('cart_items', []), request.session.get('cart', {}),
    )

    if not items_payload:
        return JsonResponse(
            {'success': False, 'error': 'В корзине нет товаров'}, status=200
        )

    logger.info('[Express] === create_express_delivery START ===')
    logger.info('[Express] destination_coords: %s', destination_coords)
    logger.info('[Express] destination_address: %s', data.get('destination_address', ''))
    logger.info('[Express] cart_items from frontend: %s', len(data.get('cart_items', [])))
    logger.info('[Express] session_cart: %s', bool(request.session.get('cart')))

    result = calculator.calculate_express(
        items_payload, destination_coords, data.get('destination_address', ''),
    )

    if result.get('success') and result.get('price'):
        return JsonResponse({
            'success': True,
            'claim_id': result.get('claim_id'),
            'price': result.get('price'),
            'currency': 'RUB',
            'expires_in_seconds': 600,
        })
    else:
        return JsonResponse({
            'success': False,
            'error': result.get('error', 'Не удалось создать заказ'),
        }, status=200)


@csrf_exempt
@require_POST
@_json_login_required
def cancel_express_delivery_view(request):
    """Cancel Express delivery order in Yandex.

    POST JSON: {"claim_id": "..."}
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'}, status=400
        )

    claim_id = data.get('claim_id', '')
    if not claim_id:
        return JsonResponse(
            {'success': False, 'error': 'Не указан claim_id'}, status=400
        )

    service = YandexDeliveryService()
    if not service.is_configured():
        return JsonResponse(
            {'success': False, 'error': 'Яндекс Доставка не настроена'}, status=200
        )

    try:
        logger.info('[Cancel] Cancel request for claim_id: %s', claim_id)
        result = service.cancel_express_claim(claim_id)
        logger.info('[Cancel] Cancel result: %s', json.dumps(result, ensure_ascii=False)[:500])

        if result.get('success'):
            return JsonResponse({
                'success': True,
                'message': result.get('message', 'Заказ отменён'),
            })
        else:
            logger.error('[Cancel] Cancel failed: %s', result.get('error'))
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Не удалось отменить заказ'),
            }, status=400)
    except Exception as e:
        logger.exception('cancel_express_delivery unexpected error')
        return JsonResponse(
            {'success': False, 'error': 'Не удалось отменить заказ'}, status=500
        )


@csrf_exempt
@require_POST
@_json_login_required
def calculate_delivery_view(request):
    """Calculate delivery price for Express and Other Day APIs.

    POST JSON:
    {
        "destination_coords": "[lon,lat]",
        "destination_address": "...",
        "delivery_type": "courier|pickup|postamat",
        "cart_items": [...]
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'}, status=400
        )

    destination_coords = _parse_coords(data.get('destination_coords'))
    if not destination_coords:
        return JsonResponse(
            {'success': False, 'error': 'Не удалось определить координаты'},
            status=400,
        )

    delivery_type = data.get('delivery_type', 'courier')
    api_type = _determine_api_type(delivery_type)

    calculator = DeliveryPriceCalculator()
    items_payload = calculator.build_items_from_cart(
        data.get('cart_items', []), request.session.get('cart', {}),
    )

    if not items_payload:
        return JsonResponse(
            {'success': False, 'error': 'В корзине нет товаров'}, status=200
        )

    if api_type == 'express':
        result = calculator.calculate_express(
            items_payload, destination_coords, data.get('destination_address', ''),
        )
    else:
        recipient = data.get('recipient', {})
        result = calculator.calculate_other_day(
            items_payload, destination_coords,
            data.get('destination_address', ''),
            delivery_type,
            pvz_id=data.get('pvz_id', ''),
            recipient_name=(
                recipient.get('first_name', '') + ' ' + recipient.get('last_name', '')
            ).strip(),
            recipient_phone=recipient.get('phone', ''),
            email=recipient.get('email', ''),
        )

    if result.get('success'):
        response_data = {
            'success': True,
            'price': result.get('price', 0),
            'currency': 'RUB',
            'delivery_days': result.get('delivery_days'),
            'api_type': api_type,
        }
        if api_type == 'express' and result.get('claim_id'):
            response_data['claim_id'] = result['claim_id']
        return JsonResponse(response_data)
    else:
        return JsonResponse({
            'success': False,
            'error': result.get('error', 'Ошибка расчёта'),
            'api_type': api_type,
        }, status=200)


@csrf_exempt
@require_POST
@_json_login_required
def offers_info_view(request):
    """Get available delivery intervals via offers/info (Other Day API).

    POST JSON:
    {
        "destination_coords": "[lon,lat]",
        "destination_address": "...",
        "delivery_type": "pickup|postamat",
        "pvz_id": "...",
        "cart_items": [...],
        "recipient": {"first_name": "...", "last_name": "...", "phone": "...", "email": "..."}
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'}, status=400
        )

    destination_coords = _parse_coords(data.get('destination_coords'))
    if not destination_coords:
        return JsonResponse(
            {'success': False, 'error': 'Не удалось определить координаты'},
            status=400,
        )

    delivery_type = data.get('delivery_type', 'pickup')
    pvz_id = data.get('pvz_id') or ''
    recipient = data.get('recipient', {})

    calculator = DeliveryPriceCalculator()
    items_payload = calculator.build_items_from_cart(
        data.get('cart_items', []), request.session.get('cart', {}),
    )

    if not items_payload:
        return JsonResponse(
            {'success': False, 'error': 'В корзине нет товаров'}, status=200
        )

    result = calculator.get_offers_with_price(
        items_payload, destination_coords,
        data.get('destination_address', ''),
        delivery_type, pvz_id,
        recipient_name=(
            recipient.get('first_name', '') + ' ' + recipient.get('last_name', '')
        ).strip(),
        recipient_phone=recipient.get('phone', ''),
        email=recipient.get('email', ''),
    )

    if not result.get('success'):
        return JsonResponse({
            'success': False,
            'error': result.get('error', 'Не удалось получить интервалы'),
        }, status=200)

    return JsonResponse(result)


@login_required
def postamats_list_view(request):
    """Return postamat (terminal) list from Yandex Delivery API."""
    service = YandexDeliveryService()

    try:
        radius_km = float(request.GET.get('radius_km', 50))
        max_results = int(request.GET.get('max_results', 500))
    except (ValueError, TypeError):
        return JsonResponse({
            'success': False, 'points': [], 'count': 0,
            'error': 'Некорректные параметры запроса',
        }, status=400)

    radius_km = max(1, min(radius_km, 200))
    max_results = max(1, min(max_results, 1000))

    result = service.get_postamats(
        operator_ids=['market_l4g'],
        center_lat=float(getattr(settings, 'YANDEX_SHOP_LAT', 53.216940239129094)),
        center_lon=float(getattr(settings, 'YANDEX_SHOP_LON', 50.162688008923745)),
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
            'success': False, 'points': [], 'count': 0,
            'error': result.get('error', 'Не удалось получить постоматы'),
        }, status=200)


@login_required
def packages_list_view(request):
    """Return all Package records for frontend tare weight lookup."""
    packages = list(Package.objects.values(
        'weight_range', 'length', 'width', 'height', 'tare_weight',
    ))
    return JsonResponse({'success': True, 'packages': packages})


@login_required
def pvz_locations_view(request):
    """Return PVZ list from Yandex Delivery API."""
    delivery_type = request.GET.get('type', 'pvz')

    service = YandexDeliveryService()
    cache_key = f'pvz_locations_{delivery_type}'

    from django.core.cache import cache
    cached = cache.get(cache_key)
    if cached:
        points = cached.get('points', [])
        if delivery_type == 'pvz':
            points = [p for p in points if p.get('type') == 'pickup_point']
        return JsonResponse({
            'success': True,
            'points': points,
            'count': len(points),
        })

    max_retries = 3
    for attempt in range(max_retries):
        result = service.get_pickup_points(
            operator_ids=['market_l4g'],
            point_type='pickup_point',
            center_lat=float(getattr(settings, 'YANDEX_SHOP_LAT', 53.216940239129094)),
            center_lon=float(getattr(settings, 'YANDEX_SHOP_LON', 50.162688008923745)),
            radius_km=50,
            max_results=500,
        )

        if result.get('success'):
            cache.set(cache_key, result, 3600)
            break

        error = result.get('error', '')
        if '429' in error or 'rate' in error.lower():
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                logger.warning(
                    'pvz_locations: rate limited, retrying in %ds (attempt %d/%d)',
                    wait_time, attempt + 1, max_retries,
                )
                time.sleep(wait_time)
                continue
        break

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
            'success': False, 'points': [], 'count': 0,
            'error': result.get('error', 'Не удалось получить точки выдачи'),
        }, status=200)


@csrf_exempt
@require_POST
@_json_login_required
def geocode_address_view(request):
    """Geocode addresses via Yandex Geocoder API.

    POST JSON: {"query": "Самара ул Революционная 3"}
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'}, status=400
        )

    query = data.get('query', '').strip()
    if not query:
        return JsonResponse(
            {'success': False, 'error': 'Запрос пустой'}, status=400
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


@csrf_exempt
@require_POST
def yandex_delivery_webhook(request):
    """Webhook endpoint for Yandex Delivery widget."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return HttpResponse(
            '<html><body>OK</body></html>',
            content_type='text/html',
            status=200,
        )

    point_id = data.get('id') or data.get('point_id', '')
    point_type = data.get('type', '')
    point_name = data.get('name', '') or data.get('title', '')
    point_address = data.get('address', '') or data.get('full_address', '')

    payload = data.get('payload', data)
    if not point_id:
        point_id = payload.get('id') or payload.get('point_id', '')
    if not point_address:
        point_address = payload.get('address', '') or payload.get('full_address', '')
    if not point_name:
        point_name = payload.get('name', '') or payload.get('title', '')

    logger.info(
        'Yandex Delivery webhook: id=%s type=%s address=%s',
        point_id, point_type, point_address,
    )

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
    """Integration status page for Yandex Delivery."""
    service = YandexDeliveryService()

    return JsonResponse({
        'configured': service.is_configured(),
        'test_mode': service.test_mode,
        'shop_address': service.shop_address,
        'shop_coordinates': [service.shop_lon, service.shop_lat],
        'express_base_url': service.express_base_url,
        'platform_base_url': service.platform_base_url,
    })


@login_required
@require_POST
def refresh_order_status_view(request, order_id):
    """Manually refresh Yandex Delivery status for a specific order."""
    order = get_object_or_404(Order, pk=order_id, user=request.user)

    if order.delivery_method != Order.DeliveryMethod.DELIVERY:
        return JsonResponse({
            'success': False,
            'error': 'У этого заказа не используется доставка Яндекс',
        })

    service = YandexDeliveryService()
    if not service.is_configured():
        return JsonResponse({
            'success': False,
            'error': 'Яндекс Доставка не настроена',
        })

    yandex_status = None

    if order.delivery_api_type == 'express' and order.express_claim_id:
        result = service.get_express_claim_info(order.express_claim_id)
        if result.get('success'):
            yandex_status = result.get('status')
    elif order.delivery_api_type == 'other_day' and order.yandex_order_id:
        result = service.get_request_info(order.yandex_order_id)
        if result.get('success'):
            yandex_status = result.get('status')

    if yandex_status is None:
        return JsonResponse({
            'success': False,
            'error': 'Не удалось получить статус из Яндекс Доставки',
        })

    order.yandex_delivery_status = yandex_status.lower() if yandex_status else ''
    order.yandex_delivery_status_raw = yandex_status
    order.yandex_delivery_status_updated_at = timezone.now()

    from coffee_shop.tasks import _map_yandex_status_to_order

    order_status, is_final = _map_yandex_status_to_order(
        yandex_status, api_type=order.delivery_api_type
    )

    save_fields = [
        'yandex_delivery_status',
        'yandex_delivery_status_raw',
        'yandex_delivery_status_updated_at',
    ]
    if order_status:
        old_status = order.status
        order.status = order_status
        save_fields.append('status')

    order.save(update_fields=save_fields)

    if order_status and old_status != order_status:
        from coffee_shop.tasks import send_order_status_changed_email
        send_order_status_changed_email.delay(order.pk, order_status)

    return JsonResponse({
        'success': True,
        'yandex_status': yandex_status,
        'order_status': order.status,
        'order_status_display': order.get_status_display(),
    })
