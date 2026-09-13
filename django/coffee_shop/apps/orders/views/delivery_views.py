"""Yandex Delivery views — Express + Other Day API integration."""
import json
import logging
import time
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


def _determine_api_type(delivery_type):
    """Determine which API to use based on delivery type.

    Courier → Express API (same-day)
    PVZ/Postamat → Other Day API (scheduled)
    """
    if delivery_type in ('pickup', 'postamat'):
        return 'other_day'
    return 'express'


@csrf_exempt
@require_POST
def create_express_delivery_view(request):
    """Create Express delivery order in Yandex.

    This creates and accepts a claim, then gets the price.
    Returns claim_id for later confirmation/cancellation.

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
        "expires_in_seconds": 600  // 10 minutes
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'}, status=400
        )

    destination_coords = data.get('destination_coords')
    destination_address = data.get('destination_address', '')
    delivery_type = data.get('delivery_type', 'courier')

    # Parse coordinates
    if isinstance(destination_coords, str):
        geocoder = YandexGeocoderService()
        parsed = geocoder.parse_coords(destination_coords)
        if parsed is None:
            return JsonResponse(
                {'success': False, 'error': 'Некорректный формат координат'},
                status=400
            )
        destination_coords = parsed
    elif isinstance(destination_coords, list):
        try:
            destination_coords = [float(destination_coords[0]), float(destination_coords[1])]
        except (ValueError, IndexError):
            return JsonResponse(
                {'success': False, 'error': 'Некорректный формат координат'},
                status=400
            )

    if not destination_coords:
        return JsonResponse(
            {'success': False, 'error': 'Не удалось определить координаты'},
            status=400
        )

    if delivery_type != 'courier':
        return JsonResponse(
            {'success': False, 'error': 'Только курьерская доставка'},
            status=400
        )

    service = YandexDeliveryService()
    if not service.is_configured():
        logger.warning('create_express: Yandex Delivery not configured')
        return JsonResponse(
            {'success': False, 'error': 'Яндекс Доставка не настроена'}, status=200
        )

    try:
        logger.info('[Express] === create_express_delivery START ===')
        logger.info('[Express] destination_coords: %s', destination_coords)
        logger.info('[Express] destination_address: %s', destination_address)
        logger.info('[Express] cart_items from frontend: %s', len(data.get('cart_items', [])))
        logger.info('[Express] session_cart: %s', bool(request.session.get('cart')))

        cart_items_from_frontend = data.get('cart_items', [])
        session_cart = request.session.get('cart', {})

        items_payload = _build_items_from_cart(
            cart_items_from_frontend, session_cart
        )
        logger.info('[Express] items_payload: %s', items_payload)

        if not items_payload:
            return JsonResponse(
                {'success': False, 'error': 'В корзине нет товаров'}, status=200
            )

        # Create claim to get price (accept happens on payment confirmation)
        logger.info('[Express] Calling _calculate_express_price')
        result = _calculate_express_price(service, items_payload,
                                          destination_coords, destination_address)
        logger.info('[Express] _calculate_express_price result: %s', result)

        if result.get('success') and result.get('price'):
            return JsonResponse({
                'success': True,
                'claim_id': result.get('claim_id'),
                'price': result.get('price'),
                'currency': 'RUB',
                'expires_in_seconds': 600,  # 10 minutes
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Не удалось создать заказ'),
            }, status=200)

    except Exception as e:
        logger.exception('create_express_delivery unexpected error')
        return JsonResponse(
            {'success': False, 'error': 'Внутренняя ошибка сервера'}, status=500
        )


@csrf_exempt
@require_POST
def cancel_express_delivery_view(request):
    """Cancel Express delivery order in Yandex.

    POST JSON:
    {
        "claim_id": "..."
    }

    Returns:
    {
        "success": true,
        "message": "Заказ отменён"
    }
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
        # Try to cancel the claim
        # Note: Yandex Express API may not have direct cancel endpoint
        # We'll use claims/accept with cancel state if available
        result = service.cancel_express_claim(claim_id)

        if result.get('success'):
            return JsonResponse({
                'success': True,
                'message': 'Заказ отменён',
            })
        else:
            # Don't fail if cancel is not supported
            logger.warning('cancel_express: %s', result.get('error'))
            return JsonResponse({
                'success': True,
                'message': 'Заказ отменён',
            })

    except Exception as e:
        logger.exception('cancel_express_delivery unexpected error')
        return JsonResponse(
            {'success': False, 'error': 'Не удалось отменить заказ'}, status=500
        )


@csrf_exempt
@require_POST
def calculate_delivery_view(request):
    """Calculate delivery price for Express and Other Day APIs.

    For Express: price is returned in claims/create response.
    For Other Day: price is returned in offers/create response.

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

    destination_coords = data.get('destination_coords')
    destination_address = data.get('destination_address', '')
    delivery_type = data.get('delivery_type', 'courier')

    # Parse coordinates from string "lon,lat" or list [lon, lat]
    if isinstance(destination_coords, str):
        geocoder = YandexGeocoderService()
        parsed = geocoder.parse_coords(destination_coords)
        if parsed is None:
            return JsonResponse(
                {'success': False, 'error': 'Некорректный формат координат'},
                status=400
            )
        destination_coords = parsed
    elif isinstance(destination_coords, list):
        try:
            destination_coords = [float(destination_coords[0]), float(destination_coords[1])]
        except (ValueError, IndexError):
            return JsonResponse(
                {'success': False, 'error': 'Некорректный формат координат'},
                status=400
            )

    if not destination_coords:
        return JsonResponse(
            {'success': False, 'error': 'Не удалось определить координаты'},
            status=400
        )

    api_type = _determine_api_type(delivery_type)
    service = YandexDeliveryService()

    if not service.is_configured():
        logger.warning('calculate_delivery: Yandex Delivery not configured')
        return JsonResponse(
            {'success': False, 'error': 'Яндекс Доставка не настроена'}, status=200
        )

    try:
        cart_items_from_frontend = data.get('cart_items', [])
        session_cart = request.session.get('cart', {})

        if not cart_items_from_frontend and not session_cart:
            return JsonResponse(
                {'success': False, 'error': 'Корзина пуста'}, status=200
            )

        items_payload = _build_items_from_cart(
            cart_items_from_frontend, session_cart
        )

        if not items_payload:
            return JsonResponse(
                {'success': False, 'error': 'В корзине нет товаров'}, status=200
            )

        if api_type == 'express':
            # Express API — price comes from claims/create
            result = _calculate_express_price(service, items_payload,
                                              destination_coords, destination_address)
        else:
            # Other Day API — price comes from offers/create
            pvz_id = data.get('pvz_id') or ''
            recipient = data.get('recipient', {})
            logger.info('[OtherDay] calculate_delivery: pvz_id=%s, delivery_type=%s', pvz_id, delivery_type)
            logger.info('[OtherDay] items_payload: %s', json.dumps(items_payload, ensure_ascii=False))
            logger.info('[OtherDay] destination_coords: %s', destination_coords)
            logger.info('[OtherDay] destination_address: %s', destination_address)
            logger.info('[OtherDay] recipient: %s', json.dumps(recipient, ensure_ascii=False))
            result = _calculate_other_day_price(
                service, items_payload, destination_coords, destination_address,
                delivery_type, pvz_id,
                recipient_name=recipient.get('first_name', '') + ' ' + recipient.get('last_name', ''),
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
            # Возвращаем claim_id для Express API (чтобы использовать при оформлении)
            if api_type == 'express' and result.get('claim_id'):
                response_data['claim_id'] = result['claim_id']
            return JsonResponse(response_data)
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Ошибка расчёта'),
                'api_type': api_type,
            }, status=200)

    except Exception as e:
        logger.exception('calculate_delivery unexpected error')
        return JsonResponse(
            {'success': False, 'error': 'Внутренняя ошибка сервера'}, status=500
        )


def _build_items_from_cart(cart_items_frontend, session_cart):
    """Build items payload from cart data."""
    if cart_items_frontend:
        total_weight_grams = 0
        total_quantity = 0
        for item in cart_items_frontend:
            try:
                weight_grams = int(item.get('weight', 0))
                quantity = int(item.get('quantity', 1))
                total_weight_grams += weight_grams * quantity
                total_quantity += quantity
            except (ValueError, TypeError):
                continue

        if total_weight_grams > 0:
            package = Package.for_weight(total_weight_grams)
            total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)
            return [{
                'quantity': total_quantity,
                'weight': round(total_weight_kg, 3),
                'size': {
                    'length': float(package.length),
                    'width': float(package.width),
                    'height': float(package.height),
                },
                'title': 'Товар',
            }]
    else:
        total_weight_grams = 0
        total_quantity = 0
        product_name = 'Товар'
        for key, value in session_cart.items():
            try:
                from coffee_shop.apps.catalog.models import Product
                product = Product.objects.get(pk=value['product_id'])
                weight_grams = int(value.get('weight', 0))
                quantity = int(value.get('quantity', 1))
                total_weight_grams += weight_grams * quantity
                total_quantity += quantity
                product_name = product.name
            except (Product.DoesNotExist, ValueError):
                continue

        if total_weight_grams > 0:
            package = Package.for_weight(total_weight_grams)
            total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)
            return [{
                'quantity': total_quantity,
                'weight': round(total_weight_kg, 3),
                'size': {
                    'length': float(package.length),
                    'width': float(package.width),
                    'height': float(package.height),
                },
                'title': product_name,
            }]

    return []


def _calculate_express_price(service, items_payload, destination_coords,
                             destination_address):
    """Calculate Express delivery price via claims/create.

    Express API requires:
    - items must have pickup_point and droppof_point (referencing point_ids)
    - route_points must have contact with name and phone
    - address must have fullname and coordinates [lon, lat]

    IMPORTANT: We only CREATE the claim to get the price.
    We do NOT accept it - that happens later when user confirms delivery.
    """
    # Build Express items with required pickup_point/droppof_point references
    size = items_payload[0].get('size', {})
    items = [{
        'title': items_payload[0].get('title', 'Товар'),
        'quantity': items_payload[0].get('quantity', 1),
        'cost_value': '0',
        'cost_currency': 'RUB',
        'pickup_point': 1,
        'droppof_point': 2,
        'size': {
            'length': float(size.get('length', 0.12)),
            'width': float(size.get('width', 0.06)),
            'height': float(size.get('height', 0.06)),
        },
        'weight': float(items_payload[0].get('weight', 0.1)),
    }]

    route_points = [
        {
            'point_id': 1,
            'visit_order': 1,
            'type': 'source',
            'contact': {
                'name': 'Магазин',
                'phone': '+79000000000',
            },
            'address': {
                'fullname': service.shop_address,
                'coordinates': [service.shop_lon, service.shop_lat],
            },
        },
        {
            'point_id': 2,
            'visit_order': 2,
            'type': 'destination',
            'contact': {
                'name': 'Клиент',
                'phone': '+79000000000',
            },
            'address': {
                'fullname': destination_address,
                'coordinates': destination_coords,
            },
        },
    ]

    # Log the payload for debugging
    logger.info('[Express] Creating claim for price estimate:')
    logger.info('[Express]   items: %s', json.dumps(items, ensure_ascii=False))
    logger.info('[Express]   route_points: %s', json.dumps(route_points, ensure_ascii=False))

    # Step 1: Create claim
    result = service.create_express_claim(
        items=items,
        route_points=route_points,
        client_requirements={'taxi_class': 'courier'},
    )

    if not result.get('success'):
        logger.error('[Express] Claim creation failed: %s', result.get('error'))
        return {'success': False, 'error': result.get('error')}

    claim_id = result.get('claim_id')
    if not claim_id:
        logger.error('[Express] No claim_id in response')
        return {'success': False, 'error': 'Нет claim_id в ответе API'}

    logger.info('[Express] Claim created: %s, polling for price...', claim_id)

    # Step 2: Poll claims/info until status is ready_for_approval (price available)
    # Lifecycle: new -> estimating -> ready_for_approval (price in pricing.offer.price)
    max_polls = 30  # 30 * 2s = 60s timeout
    version = 1
    price = '0'
    for i in range(max_polls):
        time.sleep(2)
        info_result = service.get_express_claim_info(claim_id)
        if not info_result.get('success'):
            logger.warning('[Express] claims/info failed (attempt %d/%d): %s', i + 1, max_polls, info_result.get('error'))
            continue

        raw = info_result.get('raw', {})
        status = raw.get('status', '')
        version = raw.get('version', version)

        logger.info('[Express] Poll %d: status=%s, version=%d', i + 1, status, version)

        if status == 'ready_for_approval':
            pricing = raw.get('pricing', {})
            if isinstance(pricing, dict):
                offer = pricing.get('offer', {})
                if isinstance(offer, dict):
                    price = offer.get('price', '0')
                    currency = pricing.get('currency', 'RUB')
                    logger.info('[Express] Price found: %s %s', price, currency)
            if price and price != '0':
                logger.info('[Express] Price ready after %d polls', i + 1)
                break
            else:
                logger.warning('[Express] ready_for_approval but price=0, continuing...')
        elif status in ('estimating', 'new'):
            logger.info('[Express] Still estimating (status: %s)...', status)
        elif status == 'estimating_failed':
            error_msgs = raw.get('error_messages', [])
            msg = '; '.join(error_msgs) if error_msgs else 'Unknown error'
            logger.error('[Express] Estimating failed: %s', msg)
            return {'success': False, 'error': f'Не удалось оценить заявку: {msg}'}
        elif status in ('failed', 'canceled'):
            logger.error('[Express] Claim entered terminal state: %s', status)
            return {'success': False, 'error': 'Заявка отменена или завершилась ошибкой'}
    else:
        logger.error('[Express] Price polling timed out after %d attempts', max_polls)
        return {'success': False, 'error': 'Не удалось получить цену: таймаут ожидания оценки'}

    # Step 3: Claim is NOT accepted here.
    # Accept happens later when user confirms payment (payment_webhook / payment_result).

    if price and price != '0':
        logger.info('[Express] Price estimate: %s RUB, claim_id: %s', price, claim_id)
        return {
            'success': True,
            'price': price,
            'delivery_days': 1,
            'claim_id': claim_id,
        }
    else:
        logger.error('[Express] Could not get price after accept. Raw: %s',
                     json.dumps(raw, ensure_ascii=False)[:500])
        return {'success': False, 'error': 'Не удалось получить цену доставки'}


def _calculate_other_day_price(service, items_payload, destination_coords,
                               destination_address, delivery_type, pvz_id='',
                               recipient_name='', recipient_phone='', email=''):
    """Calculate Other Day delivery price via offers/create.

    items_payload comes from frontend in Express format:
    [{'quantity': N, 'weight': W, 'size': {...}, 'title': '...'}]

    We need to convert to Other Day format with billing_details and places.
    """
    # Use PVZ ID from frontend (user-selected PVZ), fallback to shop PVZ
    if not pvz_id and delivery_type in ('pickup', 'postamat'):
        pvz_id = service.pvz_id

    # Convert items from Express format to Other Day format
    if items_payload and items_payload[0]:
        first_item = items_payload[0]
        size = first_item.get('size', {})
        quantity = int(first_item.get('quantity', 1))
        weight = float(first_item.get('weight', 0.1))

        # Build items for Other Day API
        inn = getattr(settings, 'YANDEX_MERCHANT_INN', '7707083893')
        unit_price_kopecks = 150000  # fallback 1500 RUB
        place_barcode = f'BOX-001'  # common barcode for the box

        other_day_items = [{
            'count': quantity,
            'name': first_item.get('title', 'Товар'),
            'article': 'coffee-item',
            'billing_details': {
                'unit_price': unit_price_kopecks,
                'assessed_unit_price': unit_price_kopecks,
                'inn': inn,
                'nds': 20,
            },
            'physical_dims': {
                'dx': int(float(size.get('length', 0.12)) * 100),
                'dy': int(float(size.get('width', 0.06)) * 100),
                'dz': int(float(size.get('height', 0.06)) * 100),
            },
            'place_barcode': place_barcode,
        }]

        # Build places (top-level in Other Day API)
        # barcode MUST match place_barcode in items
        other_day_places = [{
            'barcode': place_barcode,
            'physical_dims': {
                'weight_gross': int(weight * 1000) + 500,  # add tare
                'dx': int(float(size.get('length', 0.12)) * 100),
                'dy': int(float(size.get('width', 0.06)) * 100),
                'dz': int(float(size.get('height', 0.06)) * 100),
            },
        }]
    else:
        other_day_items = []
        other_day_places = []

    # Build source and destination
    if delivery_type in ('pickup', 'postamat'):
        last_mile_policy = 'self_pickup'
        source_point = {
            'platform_station': {
                'platform_id': service.pvz_id,
            },
        }
        destination_point = {
            'type': 'platform_station',
            'platform_station': {
                'platform_id': pvz_id or service.pvz_id,
            },
        }
        logger.info('[OtherDay] === PAYLOAD ===')
        logger.info('[OtherDay] source_point: %s', json.dumps(source_point, ensure_ascii=False))
        logger.info('[OtherDay] destination_point: %s', json.dumps(destination_point, ensure_ascii=False))
        logger.info('[OtherDay] pvz_id (selected): %s', pvz_id)
        logger.info('[OtherDay] service.pvz_id (source): %s', service.pvz_id)
    else:
        last_mile_policy = 'time_interval'
        source_point = {
            'platform_station': {
                'platform_id': service.test_warehouse_id or service.pvz_id,
            },
        }
        destination_point = {
            'type': 'custom_location',
            'custom_location': {
                'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                'details': {'full_address': destination_address},
            },
        }

    # Build complete payload
    name_parts = recipient_name.split() if recipient_name else ['', '']
    recipient_info = {
        'first_name': name_parts[0] if name_parts else 'Клиент',
        'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
        'phone': recipient_phone or '+79000000000',
        'email': email or '',
    }

    payload = {
        'info': {
            'operator_request_id': 'estimate-' + str(timezone.now().timestamp()),
            'comment': 'Расчёт стоимости доставки',
        },
        'source': source_point,
        'destination': destination_point,
        'items': other_day_items,
        'places': other_day_places,
        'billing_info': {
            'payment_method': 'already_paid',
            'delivery_cost': 0,
        },
        'recipient_info': recipient_info,
        'last_mile_policy': last_mile_policy,
        'particular_items_refuse': False,
        'forbid_unboxing': False,
    }

    try:
        create_url = f'{service.platform_base_url}/offers/create'
        response = service._post(create_url, payload)
        data = response.json()

        logger.info('[OtherDay] === API response ===')
        logger.info('[OtherDay] Full response: %s', json.dumps(data, ensure_ascii=False)[:2000])

        offers = data.get('offers', [])
        if offers:
            offer = offers[0]
            offer_details = offer.get('offer_details', {})
            logger.info('[OtherDay] offer_details: %s', json.dumps(offer_details, ensure_ascii=False)[:1000])

            # API returns pricing as string: "1717.15 RUB"
            pricing = offer_details.get('pricing', '0')
            logger.info('[OtherDay] pricing raw: %s', repr(pricing))

            try:
                price = float(pricing.split()[0])
            except (ValueError, IndexError, TypeError):
                price = 0

            logger.info('[OtherDay] Final price: %s', price)

            return {
                'success': True,
                'price': str(price),
                'delivery_days': 1,
            }
        return {'success': False, 'error': 'Нет доступных офферов'}

    except Exception as e:
        logger.error('[OtherDay] Price calculation error: %s', e)
        return {'success': False, 'error': str(e)}


@csrf_exempt
@require_POST
def offers_info_view(request):
    """Get available delivery intervals via offers/info (Other Day API).

    If no valid intervals available, creates order via request/create
    and returns delivery date/price immediately.

    POST JSON:
    {
        "destination_coords": "[lon,lat]",
        "destination_address": "...",
        "delivery_type": "pickup|postamat",
        "pvz_id": "...",
        "cart_items": [...],
        "recipient": {"first_name": "...", "last_name": "...", "phone": "...", "email": "..."}
    }

    Returns:
    {
        "success": true,
        "offers": [...],  // if intervals available
        OR
        {
            "success": true,
            "created": true,
            "request_id": "...",
            "price": "...",
            "delivery_date": "15.09.2026",
            "delivery_time": "10:00–14:00",
            "status": "new"
        }
    }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse(
            {'success': False, 'error': 'Некорректные данные'}, status=400
        )

    destination_coords = data.get('destination_coords')
    destination_address = data.get('destination_address', '')
    delivery_type = data.get('delivery_type', 'pickup')
    pvz_id = data.get('pvz_id') or ''
    recipient = data.get('recipient', {})

    # Parse coordinates
    if isinstance(destination_coords, str):
        geocoder = YandexGeocoderService()
        parsed = geocoder.parse_coords(destination_coords)
        if parsed is None:
            return JsonResponse(
                {'success': False, 'error': 'Некорректный формат координат'},
                status=400
            )
        destination_coords = parsed
    elif isinstance(destination_coords, list):
        try:
            destination_coords = [float(destination_coords[0]), float(destination_coords[1])]
        except (ValueError, IndexError):
            return JsonResponse(
                {'success': False, 'error': 'Некорректный формат координат'},
                status=400
            )

    if not destination_coords:
        return JsonResponse(
            {'success': False, 'error': 'Не удалось определить координаты'},
            status=400
        )

    service = YandexDeliveryService()
    if not service.is_configured():
        logger.warning('offers_info: Yandex Delivery not configured')
        return JsonResponse(
            {'success': False, 'error': 'Яндекс Доставка не настроена'}, status=200
        )

    try:
        cart_items_from_frontend = data.get('cart_items', [])
        session_cart = request.session.get('cart', {})

        if not cart_items_from_frontend and not session_cart:
            return JsonResponse(
                {'success': False, 'error': 'Корзина пуста'}, status=200
            )

        items_payload = _build_items_from_cart(
            cart_items_from_frontend, session_cart
        )

        if not items_payload:
            return JsonResponse(
                {'success': False, 'error': 'В корзине нет товаров'}, status=200
            )

        # Convert to Other Day format
        inn = getattr(settings, 'YANDEX_MERCHANT_INN', '7707083893')
        first_item = items_payload[0]
        size = first_item.get('size', {})
        quantity = int(first_item.get('quantity', 1))
        weight = float(first_item.get('weight', 0.1))

        # Get real price from cart_items (in kopecks)
        cart_items_from_frontend = data.get('cart_items', [])
        unit_price_kopecks = 150000  # fallback
        if cart_items_from_frontend and len(cart_items_from_frontend) > 0:
            try:
                # cart items have 'price' in rubles (e.g. 500.00)
                cart_price_rub = float(cart_items_from_frontend[0].get('price', 0))
                unit_price_kopecks = int(cart_price_rub * 100)
            except (ValueError, TypeError, IndexError):
                pass

        place_barcode = f'BOX-001'

        other_day_items = [{
            'count': quantity,
            'name': first_item.get('title', 'Товар'),
            'article': 'coffee-item',
            'billing_details': {
                'unit_price': unit_price_kopecks,
                'assessed_unit_price': unit_price_kopecks,
                'inn': inn,
                'nds': 20,
            },
            'physical_dims': {
                'dx': int(float(size.get('length', 0.12)) * 100),
                'dy': int(float(size.get('width', 0.06)) * 100),
                'dz': int(float(size.get('height', 0.06)) * 100),
            },
            'place_barcode': place_barcode,
        }]

        # weight is in kg (from frontend Express format)
        # Convert to grams - this is already total weight (product + tare)
        total_weight_g = int(weight * 1000)

        other_day_places = [{
            'barcode': place_barcode,
            'physical_dims': {
                'weight_gross': total_weight_g,
                'dx': int(float(size.get('length', 0.12)) * 100),
                'dy': int(float(size.get('width', 0.06)) * 100),
                'dz': int(float(size.get('height', 0.06)) * 100),
            },
        }]

        # Build source/destination
        if delivery_type in ('pickup', 'postamat'):
            source_point = {
                'platform_station': {
                    'platform_id': service.pvz_id,
                },
            }
            destination_point = {
                'type': 'platform_station',
                'platform_station': {
                    'platform_id': pvz_id or service.pvz_id,
                },
            }
        else:
            source_point = {
                'platform_station': {
                    'platform_id': service.test_warehouse_id or service.pvz_id,
                },
            }
            destination_point = {
                'type': 'custom_location',
                'custom_location': {
                    'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                    'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                    'details': {'full_address': destination_address},
                },
            }

        name_parts = (recipient.get('first_name', '') + ' ' + recipient.get('last_name', '')).split()
        recipient_info = {
            'first_name': name_parts[0] if name_parts else 'Клиент',
            'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
            'phone': recipient.get('phone', '') or '+79000000000',
            'email': recipient.get('email', ''),
        }

        payload = {
            'info': {
                'operator_request_id': 'offers-info-' + str(timezone.now().timestamp()),
                'comment': 'Доступные интервалы доставки',
            },
            'source': source_point,
            'destination': destination_point,
            'items': other_day_items,
            'places': other_day_places,
            'billing_info': {
                'payment_method': 'already_paid',
                'delivery_cost': 0,
            },
            'recipient_info': recipient_info,
            'last_mile_policy': 'self_pickup' if delivery_type in ('pickup', 'postamat') else 'time_interval',
            'particular_items_refuse': False,
            'forbid_unboxing': False,
        }

        result = service.get_offers_info(
            items_data=other_day_items,
            places_data=other_day_places,
            client_order_id=payload['info']['operator_request_id'],
            destination_coords=destination_coords,
            destination_address=destination_address,
            delivery_type=delivery_type,
            pvz_id=pvz_id,
            recipient_name=recipient.get('first_name', '') + ' ' + recipient.get('last_name', ''),
            recipient_phone=recipient.get('phone', ''),
            email=recipient.get('email', ''),
        )

        if not result.get('success'):
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Не удалось получить интервалы'),
            }, status=200)

        # Filter offers with valid intervals (delivery_interval.from must exist)
        valid_offers = [
            o for o in result.get('offers', [])
            if o.get('offer_details', {}).get('delivery_interval', {}).get('min')
        ]

        if not valid_offers:
            # No valid intervals — create order via request/create
            logger.info('[offers_info] No valid intervals, creating order via request/create')

            # Build request/create payload
            request_payload = {
                'info': {
                    'operator_request_id': 'request-create-' + str(timezone.now().timestamp()),
                    'comment': 'Доставка ПВЗ→ПВЗ, ближайшее доступное время',
                },
                'source': {
                    'platform_station': {
                        'platform_id': service.pvz_id,
                    },
                },
                'destination': {
                    'type': 'platform_station',
                    'platform_station': {
                        'platform_id': pvz_id or service.pvz_id,
                    },
                },
                'items': other_day_items,
                'places': other_day_places,
                'recipient_info': recipient_info,
                'billing_info': {
                    'payment_method': 'already_paid',
                    'delivery_cost': 0,
                },
                'last_mile_policy': 'self_pickup',
            }

            request_url = f'{service.platform_base_url}/request/create'
            resp = service._post(request_url, request_payload)
            created = resp.json()

            request_id = created.get('request_id')
            if not request_id:
                return JsonResponse({
                    'success': False,
                    'error': 'Нет request_id в ответе request/create',
                }, status=200)

            # Poll request/info for price and interval
            import time
            order_info = None
            for attempt in range(10):
                time.sleep(3)
                tracking = service.get_request_info(request_id)
                if not tracking.get('success'):
                    continue
                order_info = tracking.get('raw', {})
                status = order_info.get('status', '')
                pricing = order_info.get('pricing', {})
                interval = order_info.get('delivery_interval', {})
                if pricing.get('total') or interval.get('from') or status == 'failed':
                    break

            if not order_info:
                return JsonResponse({
                    'success': False,
                    'error': 'Не удалось получить данные заказа',
                }, status=200)

            if order_info.get('status') == 'failed':
                return JsonResponse({
                    'success': False,
                    'error': 'order_failed',
                    'message': str(order_info.get('error_messages', 'Заказ не создан')),
                }, status=200)

            # Format result
            di = order_info.get('delivery_interval', {})
            d_from = di.get('from')
            d_to = di.get('to')

            delivery_date = ''
            delivery_time = ''
            if d_from:
                try:
                    from datetime import datetime as dt_datetime, timedelta as dt_timedelta
                    tz_local = timezone(dt_timedelta(hours=4))
                    dt_from = dt_datetime.fromisoformat(
                        d_from.replace('Z', '+00:00')
                    ).astimezone(tz_local)
                    delivery_date = dt_from.strftime('%d.%m.%Y')
                    if d_to:
                        dt_to = dt_datetime.fromisoformat(
                            d_to.replace('Z', '+00:00')
                        ).astimezone(tz_local)
                        delivery_time = (
                            f"{dt_from.strftime('%H:%M')}–{dt_to.strftime('%H:%M')}"
                        )
                    else:
                        delivery_time = dt_from.strftime('%H:%M')
                except Exception as e:
                    logger.warning('[offers_info] Failed to parse interval: %s', e)

            pricing = order_info.get('pricing', {})
            price_total = pricing.get('total', '0')

            return JsonResponse({
                'success': True,
                'created': True,
                'request_id': request_id,
                'price': price_total,
                'delivery_date': delivery_date,
                'delivery_time': delivery_time,
                'status': order_info.get('status'),
            })

        # Valid offers exist — format and return them
        formatted_offers = []
        for offer in valid_offers:
            offer_id = offer.get('offer_id', '')
            offer_details = offer.get('offer_details', {})
            interval = offer_details.get('delivery_interval', {})
            pricing = offer_details.get('pricing', '0')

            # Parse price
            try:
                price_value = float(pricing.split()[0]) if isinstance(pricing, str) else float(pricing)
            except (ValueError, IndexError, TypeError):
                price_value = 0

            # Format interval
            interval_min = interval.get('min', '')
            interval_max = interval.get('max', '')
            formatted_interval = ''
            formatted_date = ''

            if interval_min and interval_max:
                try:
                    from datetime import datetime
                    min_dt = datetime.fromisoformat(interval_min.replace('Z', '+00:00'))
                    max_dt = datetime.fromisoformat(interval_max.replace('Z', '+00:00'))
                    time_min = min_dt.strftime('%H:%M')
                    time_max = max_dt.strftime('%H:%M')
                    formatted_interval = f'{time_min} \u2014 {time_max}'
                    date_str = min_dt.strftime('%d %B')
                    formatted_date = date_str.capitalize()
                except (ValueError, AttributeError):
                    formatted_interval = f'{interval_min} \u2014 {interval_max}'

            formatted_offers.append({
                'offer_id': offer_id,
                'interval_min': interval_min,
                'interval_max': interval_max,
                'price': str(price_value),
                'formatted_interval': formatted_interval,
                'formatted_date': formatted_date,
                'formatted_price': f'{price_value:,.2f}'.replace(',', ' ').replace('.', ',') + ' \u20bd',
            })

        return JsonResponse({
            'success': True,
            'offers': formatted_offers,
        })

    except Exception as e:
        logger.exception('offers_info unexpected error')
        return JsonResponse(
            {'success': False, 'error': 'Внутренняя ошибка сервера'}, status=500
        )


@login_required
def postamats_list_view(request):
    """Return postamat (terminal) list from Yandex Delivery API.

    GET /checkout/postamats/?radius_km=30&max_results=100
    """
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
        'weight_range', 'length', 'width', 'height', 'tare_weight'
    ))
    return JsonResponse({'success': True, 'packages': packages})


@login_required
def pvz_locations_view(request):
    """Return PVZ list from Yandex Delivery API.

    GET /checkout/pvz-locations/?type=pvz
    """
    delivery_type = request.GET.get('type', 'pvz')

    service = YandexDeliveryService()

    # Try cache first
    from django.core.cache import cache
    cache_key = f'pvz_locations_{delivery_type}'
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

    # Retry with backoff for rate limiting (429)
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
            # Cache for 1 hour
            cache.set(cache_key, result, 3600)
            break

        error = result.get('error', '')
        if '429' in error or 'rate' in error.lower():
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5  # 5s, 10s, 15s
                logger.warning(
                    'pvz_locations: rate limited, retrying in %ds (attempt %d/%d)',
                    wait_time, attempt + 1, max_retries
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

    status_info = {
        'configured': service.is_configured(),
        'test_mode': service.test_mode,
        'shop_address': service.shop_address,
        'shop_coordinates': [service.shop_lon, service.shop_lat],
        'express_base_url': service.express_base_url,
        'platform_base_url': service.platform_base_url,
    }

    return JsonResponse(status_info)
