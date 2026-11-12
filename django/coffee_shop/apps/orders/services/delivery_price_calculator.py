"""Delivery price calculation service — Express + Other Day APIs.

Handles price estimation for Yandex Delivery (Express and Other Day).
Extracted from delivery_views.py to eliminate duplication.
"""
import json
import logging
import time

from django.conf import settings
from django.utils import timezone

from coffee_shop.apps.catalog.models import Product
from coffee_shop.apps.orders.models import Package
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService

logger = logging.getLogger(__name__)


class DeliveryPriceCalculator:
    """Calculate delivery prices for Express and Other Day APIs."""

    def __init__(self):
        self.service = YandexDeliveryService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_express(self, items_payload, destination_coords,
                          destination_address):
        """Calculate Express delivery price via claims/create.

        Creates a claim, polls claims/info until price is available.
        Does NOT accept the claim — that happens on payment confirmation.

        Args:
            items_payload: List of item dicts from build_items_from_cart.
            destination_coords: [longitude, latitude].
            destination_address: Full address string.

        Returns:
            {'success': True, 'price': '...', 'claim_id': '...', ...}
        """
        if not self.service.is_configured():
            logger.warning('[DeliveryPriceCalc] Express: Yandex Delivery not configured')
            return {'success': False, 'error': 'Yandex Delivery not configured'}

        items = self._build_express_items_payload(items_payload)
        route_points = self._build_express_route_points(destination_address, destination_coords)

        logger.info('[Express] Creating claim for price estimate:')
        logger.info('[Express]   items: %s', json.dumps(items, ensure_ascii=False))
        logger.info('[Express]   route_points: %s', json.dumps(route_points, ensure_ascii=False))

        result = self.service.create_express_claim(
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

        # Poll claims/info until status is ready_for_approval (price available)
        max_polls = 30  # 30 * 2s = 60s timeout
        version = 1
        price = '0'

        for i in range(max_polls):
            time.sleep(2)
            info_result = self.service.get_express_claim_info(claim_id)
            if not info_result.get('success'):
                logger.warning(
                    '[Express] claims/info failed (attempt %d/%d): %s',
                    i + 1, max_polls, info_result.get('error'),
                )
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
            return {
                'success': False,
                'error': 'Не удалось получить цену: таймаут ожидания оценки',
            }

        if price and price != '0':
            logger.info('[Express] Price estimate: %s RUB, claim_id: %s', price, claim_id)
            return {
                'success': True,
                'price': price,
                'delivery_days': 1,
                'claim_id': claim_id,
            }
        else:
            logger.error(
                '[Express] Could not get price after accept. Raw: %s',
                json.dumps(raw, ensure_ascii=False)[:500],
            )
            return {'success': False, 'error': 'Не удалось получить цену доставки'}

    def calculate_other_day(self, items_payload, destination_coords,
                            destination_address, delivery_type, pvz_id='',
                            recipient_name='', recipient_phone='', email=''):
        """Calculate Other Day delivery price via offers/create.

        Args:
            items_payload: List of item dicts from build_items_from_cart.
            destination_coords: [longitude, latitude].
            destination_address: Full address string.
            delivery_type: 'courier' | 'pickup' | 'postamat'.
            pvz_id: PVZ platform_id (for pickup/postamat).
            recipient_name: Full name.
            recipient_phone: Phone number.
            email: Email address.

        Returns:
            {'success': True, 'price': '...', 'delivery_days': 1}
        """
        if not self.service.is_configured():
            logger.warning('[DeliveryPriceCalc] OtherDay: Yandex Delivery not configured')
            return {'success': False, 'error': 'Yandex Delivery not configured'}

        if not pvz_id and delivery_type in ('pickup', 'postamat'):
            pvz_id = self.service.pvz_id

        other_day_items, other_day_places = self._convert_to_other_day_format(
            items_payload, pvz_id
        )

        source_point, destination_point, last_mile_policy = (
            self._build_source_destination(
                delivery_type, pvz_id, destination_coords, destination_address
            )
        )

        recipient_info = self._build_recipient_info(recipient_name, recipient_phone, email)

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
            create_url = f'{self.service.platform_base_url}/offers/create'
            response = self.service._post(create_url, payload)
            data = response.json()

            logger.info('[OtherDay] === API response ===')
            logger.info('[OtherDay] Full response: %s', json.dumps(data, ensure_ascii=False)[:2000])

            offers = data.get('offers', [])
            if offers:
                offer = offers[0]
                offer_details = offer.get('offer_details', {})
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

    def get_offers_with_price(self, items_payload, destination_coords,
                              destination_address, delivery_type, pvz_id='',
                              recipient_name='', recipient_phone='', email=''):
        """Get available delivery intervals and price (offers/info + offers/create).

        Used for PVZ/postamat delivery type selection.

        Returns:
            JsonResponse-compatible dict with offers or pre-created order.
        """
        if not self.service.is_configured():
            return {
                'success': False,
                'error': 'Yandex Delivery not configured',
            }

        other_day_items, other_day_places = self._convert_to_other_day_format(
            items_payload, pvz_id
        )

        # Build source/destination
        if delivery_type in ('pickup', 'postamat'):
            source_point = {
                'platform_station_id': self.service.pickup_station_id,
            }
            destination_point = {
                'type': 'platform_station',
                'platform_station_id': pvz_id or self.service.pickup_station_id,
            }
        else:
            source_point = {
                'platform_station_id': self.service.test_warehouse_id or self.service.pvz_id,
            }
            destination_point = {
                'type': 'custom_location',
                'custom_location': {
                    'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                    'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                    'details': {'full_address': destination_address},
                },
            }

        recipient_info = self._build_recipient_info(recipient_name, recipient_phone, email)

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
            'last_mile_policy': (
                'self_pickup' if delivery_type in ('pickup', 'postamat') else 'time_interval'
            ),
            'particular_items_refuse': False,
            'forbid_unboxing': False,
        }

        result = self.service.get_offers_info(
            items_data=other_day_items,
            places_data=other_day_places,
            client_order_id=payload['info']['operator_request_id'],
            destination_coords=destination_coords,
            destination_address=destination_address,
            delivery_type=delivery_type,
            pvz_id=pvz_id,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            email=email,
        )

        if not result.get('success'):
            return {
                'success': False,
                'error': result.get('error', 'Не удалось получить интервалы'),
            }

        # Filter offers with valid intervals
        valid_offers = [
            o for o in result.get('offers', [])
            if o.get('offer_details', {}).get('delivery_interval', {}).get('from')
        ]

        logger.info(
            '[offers_info] Total offers from API: %d, valid offers: %d',
            len(result.get('offers', [])), len(valid_offers),
        )

        # offers/info doesn't include pricing — use offers/create
        logger.info('[offers_info] Using offers/create to get price')

        create_payload = {
            'info': {
                'operator_request_id': 'offers-create-' + str(timezone.now().timestamp()),
                'comment': 'Расчёт стоимости доставки',
            },
            'source': {
                'platform_station': {
                    'platform_id': self.service.pickup_station_id,
                },
            },
            'destination': {
                'type': 'platform_station',
                'platform_station': {
                    'platform_id': pvz_id or self.service.pickup_station_id,
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

        create_url = f'{self.service.platform_base_url}/offers/create'
        resp = self.service._post(create_url, create_payload)
        created = resp.json()

        logger.info('[offers_info] offers/create response: %s',
                    json.dumps(created, ensure_ascii=False)[:2000])

        offers = created.get('offers', [])
        if not offers:
            return {
                'success': False,
                'error': 'Нет доступных интервалов доставки',
            }

        offer = offers[0]
        offer_details = offer.get('offer_details', {})
        pricing_raw = offer_details.get('pricing', '0')

        try:
            price_value = float(pricing_raw.split()[0]) if isinstance(pricing_raw, str) else float(pricing_raw)
        except (ValueError, IndexError, TypeError):
            price_value = 0

        logger.info('[offers_info] Price from offers/create: %s', price_value)

        # Format interval
        interval = offer_details.get('delivery_interval', {})
        interval_min = interval.get('min', '')
        interval_max = interval.get('max', '')
        delivery_date = ''
        delivery_time = ''
        if interval_min and interval_max:
            try:
                from datetime import datetime as dt_datetime, timedelta as dt_timedelta
                tz_local = timezone(dt_timedelta(hours=4))
                dt_from = dt_datetime.fromisoformat(
                    interval_min.replace('Z', '+00:00')
                ).astimezone(tz_local)
                dt_to = dt_datetime.fromisoformat(
                    interval_max.replace('Z', '+00:00')
                ).astimezone(tz_local)
                delivery_date = dt_from.strftime('%d.%m.%Y')
                delivery_time = f"{dt_from.strftime('%H:%M')}–{dt_to.strftime('%H:%M')}"
            except Exception as e:
                logger.warning('[offers_info] Failed to parse interval: %s', e)

        return {
            'success': True,
            'created': True,
            'request_id': offer.get('offer_id', ''),
            'price': str(price_value),
            'delivery_date': delivery_date,
            'delivery_time': delivery_time,
            'status': 'pending',
            'offer_id': offer.get('offer_id', ''),
        }

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_items_from_cart(cart_items_frontend, session_cart):
        """Build items payload from cart data.

        Used for both frontend-provided cart items and session cart.

        Args:
            cart_items_frontend: List of item dicts from frontend.
            session_cart: Dict from request.session['cart'].

        Returns:
            List of item dicts with quantity, weight, size, title.
        """
        if cart_items_frontend:
            return DeliveryPriceCalculator._build_items_from_frontend(cart_items_frontend)
        else:
            return DeliveryPriceCalculator._build_items_from_session(session_cart)

    @staticmethod
    def _build_items_from_frontend(cart_items_frontend):
        """Build items from frontend cart data."""
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
            total_weight_kg = total_weight_grams / 1000.0
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
        return []

    @staticmethod
    def _build_items_from_session(session_cart):
        """Build items from session cart data."""
        total_weight_grams = 0
        total_quantity = 0
        product_name = 'Товар'

        for key, value in session_cart.items():
            try:
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
            total_weight_kg = total_weight_grams / 1000.0
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_express_items_payload(items_payload):
        """Convert items_payload to Express API format."""
        size = items_payload[0].get('size', {})
        return [{
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

    @staticmethod
    def _build_express_route_points(destination_address, destination_coords):
        """Build Express API route_points."""
        return [
            {
                'point_id': 1,
                'visit_order': 1,
                'type': 'source',
                'contact': {
                    'name': 'Магазин',
                    'phone': '+79000000000',
                },
                'address': {
                    'fullname': 'Самара, ул. Революционная, д. 3',
                    'coordinates': [50.162688008923745, 53.216940239129094],
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

    def _convert_to_other_day_format(self, items_payload, pvz_id):
        """Convert Express-format items to Other Day API format."""
        if not items_payload or not items_payload[0]:
            return [], []

        first_item = items_payload[0]
        size = first_item.get('size', {})
        quantity = int(first_item.get('quantity', 1))
        weight = float(first_item.get('weight', 0.1))

        inn = getattr(settings, 'YANDEX_MERCHANT_INN', '7707083893')
        unit_price_kopecks = 150000
        place_barcode = 'BOX-001'

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

        product_weight_grams = int(weight * 1000)
        try:
            pkg = Package.for_weight(product_weight_grams)
            tare_grams = int(float(pkg.tare_weight) * 1000)
        except Package.DoesNotExist:
            tare_grams = 0

        other_day_places = [{
            'barcode': place_barcode,
            'physical_dims': {
                'weight_gross': product_weight_grams + tare_grams,
                'dx': int(float(size.get('length', 0.12)) * 100),
                'dy': int(float(size.get('width', 0.06)) * 100),
                'dz': int(float(size.get('height', 0.06)) * 100),
            },
        }]

        return other_day_items, other_day_places

    def _build_source_destination(self, delivery_type, pvz_id,
                                  destination_coords, destination_address):
        """Build source and destination points for Other Day API."""
        if delivery_type in ('pickup', 'postamat'):
            last_mile_policy = 'self_pickup'
            source_point = {
                'platform_station_id': self.service.pickup_station_id,
            }
            destination_point = {
                'type': 'platform_station',
                'platform_station_id': pvz_id or self.service.pickup_station_id,
            }
        else:
            last_mile_policy = 'time_interval'
            source_point = {
                'platform_station_id': self.service.test_warehouse_id or self.service.pvz_id,
            }
            destination_point = {
                'type': 'custom_location',
                'custom_location': {
                    'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                    'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                    'details': {'full_address': destination_address},
                },
            }

        return source_point, destination_point, last_mile_policy

    @staticmethod
    def _build_recipient_info(recipient_name, recipient_phone, email):
        """Build recipient_info dict for Other Day API."""
        name_parts = recipient_name.split() if recipient_name else ['', '']
        phone = recipient_phone or '+79000000000'
        if not phone.startswith('+'):
            phone = '+7' + phone if phone.startswith('8') else '+7' + phone
        phone = '+' + ''.join(c for c in phone if c.isdigit())
        return {
            'first_name': name_parts[0] if name_parts else 'Клиент',
            'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
            'phone': phone,
            'email': email or '',
        }
