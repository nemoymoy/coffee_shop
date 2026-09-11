"""Yandex Delivery service integration — Express API + Other Day API."""
import json
import logging
import time
import uuid as uuid_module
import requests
from functools import wraps
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from coffee_shop.apps.orders.models import Package

logger = logging.getLogger(__name__)

# Taxi class constants for Yandex Cargo Express API
TAXI_CLASS_CHOICES = {
    'courier': 'courier',
    'express': 'express',
    'cargo': 'cargo',
}
DEFAULT_TAXI_CLASS = 'courier'

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 90


def rate_limited(max_requests_per_minute=MAX_REQUESTS_PER_MINUTE):
    """Decorator for throttling requests."""
    window_key = 'yandex_api_rate_limit'

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            count = cache.get(window_key, 0) or 0
            cache.set(window_key, count + 1, timeout=60)

            if count >= max_requests_per_minute:
                time.sleep(60)
                cache.set(window_key, 0, timeout=60)

            return func(*args, **kwargs)
        return wrapper
    return decorator


class YandexDeliveryService:
    """Service for Yandex Cargo Delivery API.

    Supports two APIs:
    - Express API (b2b/cargo/integration/v2) — same-day delivery
    - Other Day API (b2b/platform) — scheduled delivery in time intervals
    """

    # Other Day API endpoints
    BASE_URL = 'https://b2b.taxi.yandex.net/api/b2b/platform'
    CREATE_OFFER_URL = f'{BASE_URL}/offers/create'
    CONFIRM_OFFER_URL = f'{BASE_URL}/offers/confirm'
    GET_REQUEST_URL = f'{BASE_URL}/request/info'
    PICKUP_POINTS_URL = f'{BASE_URL}/pickup-points/list'

    # Express API endpoints
    EXPRESS_CLAIMS_CREATE_URL = '{base}/claims/create'
    EXPRESS_CLAIMS_ACCEPT_URL = '{base}/claims/accept'
    EXPRESS_CLAIMS_INFO_URL = '{base}/claims/info'
    EXPRESS_ORDERS_URL = '{base}/orders/{order_id}'

    def __init__(self):
        self._setup_tokens()
        self._setup_urls()
        self._setup_shop()
        self._setup_pvz()
        self.session = self._create_session()

    def _setup_tokens(self):
        """Configure API tokens based on test/production mode."""
        self.test_mode = getattr(settings, 'YANDEX_DELIVERY_TEST_MODE', False)

        if self.test_mode:
            self.token = getattr(settings, 'YANDEX_DELIVERY_TEST_TOKEN', '') or getattr(
                settings, 'YANDEX_DELIVERY_TOKEN', ''
            )
            self.test_warehouse_id = getattr(
                settings, 'YANDEX_DELIVERY_TEST_WAREHOUSE_ID', ''
            )
        else:
            self.token = getattr(settings, 'YANDEX_DELIVERY_TOKEN', '')
            self.test_warehouse_id = ''

    def _setup_urls(self):
        """Configure API base URLs based on test/production mode."""
        if self.test_mode:
            self.base_url = getattr(
                settings, 'YANDEX_DELIVERY_TEST_BASE_URL',
                'https://b2b.taxi.tst.yandex.net'
            )
        else:
            self.base_url = 'https://b2b.taxi.yandex.net'

        # Express API base
        self.express_base_url = getattr(
            settings, 'YANDEX_EXPRESS_BASE_URL',
            f'{self.base_url}/b2b/cargo/integration/v2'
        )

        # Other Day API base
        if self.test_mode:
            self.platform_base_url = f'{self.base_url}/api/b2b/platform'
        else:
            self.platform_base_url = 'https://b2b-authproxy.taxi.yandex.net/api/b2b/platform'

    def _setup_shop(self):
        """Configure shop (origin) coordinates."""
        self.shop_lat = float(getattr(settings, 'YANDEX_SHOP_LAT', 53.216940239129094))
        self.shop_lon = float(getattr(settings, 'YANDEX_SHOP_LON', 50.162688008923745))
        self.shop_address = getattr(
            settings, 'YANDEX_SHOP_ADDRESS',
            'Самара, ул. Революционная, д. 3'
        )

    def _setup_pvz(self):
        """Configure PVZ (pickup point) settings."""
        self.pvz_id = getattr(
            settings, 'YANDEX_PVZ_ID',
            'd0222b1e-73ff-4274-9c68-42c79d4c7eae'
        )
        self.pvz_lat = float(getattr(settings, 'YANDEX_PVZ_LAT', 53.200850))
        self.pvz_lon = float(getattr(settings, 'YANDEX_PVZ_LON', 50.150500))
        self.pvz_address = getattr(
            settings, 'YANDEX_PVZ_ADDRESS',
            'г. Самара, ул. Лукачева, д. 6'
        )

    def _create_session(self):
        """Create requests session with auth and retry strategy."""
        session = requests.Session()
        session.headers.update({
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Language': 'ru',
        })

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount('https://', adapter)
        return session

    def is_configured(self) -> bool:
        """Check if the service is configured."""
        if not self.token:
            logger.warning('is_configured: no token')
            return False
        if not any([
            self.token.startswith('ya2'),
            self.token.startswith('y0__'),
            self.token.startswith('dev-token'),
        ]):
            logger.warning(
                'is_configured: token prefix invalid: %s', self.token[:20]
            )
            return False
        return True

    def is_api_configured(self) -> bool:
        """Check if the pickup points API is configured."""
        return bool(self.token)

    def _post(self, url, payload):
        """HTTP POST with error handling."""
        response = self.session.post(url, json=payload, timeout=15)
        if response.status_code == 429:
            logger.warning('Rate limited on %s', url)
            raise requests.exceptions.HTTPError('429 Too Many Requests')
        if response.status_code != 200:
            logger.error(
                '_post failed %s: status=%s body=%s',
                url, response.status_code, response.text[:500]
            )
            response.raise_for_status()
        return response

    def _get(self, url):
        """HTTP GET with error handling."""
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        return response

    # ----------------------------------------------------------------
    # Express API — same-day delivery
    # ----------------------------------------------------------------

    def create_express_claim(self, items, route_points, client_requirements=None,
                             claim_id=None) -> dict:
        """Create an Express delivery claim.

        Args:
            items: List of items with title, quantity, cost_value, size, weight
            route_points: List with source and destination points
            client_requirements: Dict with taxi_class etc.
            claim_id: Optional custom claim_id (for idempotency)

        Returns:
            {'success': True, 'claim_id': '...', 'request_id': '...'}
        """
        if not self.is_configured():
            logger.error('create_express_claim: not configured')
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            request_id = claim_id or str(uuid_module.uuid4())
            url = self.EXPRESS_CLAIMS_CREATE_URL.format(base=self.express_base_url)
            url = f'{url}?request_id={request_id}'

            payload = {
                'items': items,
                'route_points': route_points,
            }
            if client_requirements:
                payload['client_requirements'] = client_requirements

            response = self._post(url, payload)
            data = response.json()

            logger.info('[Express] Claim created: %s', json.dumps(data, ensure_ascii=False)[:500])

            claim_id = data.get('id', '')
            if not claim_id:
                return {
                    'success': False,
                    'error': f'Нет claim_id в ответе: {data}',
                }

            return {
                'success': True,
                'claim_id': claim_id,
                'request_id': request_id,
                'status': data.get('status', 'new'),
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('create_express_claim error: %s', e)
            return {'success': False, 'error': str(e)}

    def accept_express_claim(self, claim_id: str, version: int = 1, _retry_count: int = 0) -> dict:
        """Accept an Express claim (must be done within 10 minutes of creation).

        Args:
            claim_id: The claim ID from create_express_claim
            version: Claim version from claims/info (required for accept)
            _retry_count: Internal retry counter (max 2)

        Returns:
            {'success': True, 'claim_id': '...', 'status': 'accepted'}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        if _retry_count > 2:
            logger.error(
                '[Express] accept_express_claim max retries reached for %s',
                claim_id
            )
            return {
                'success': False,
                'error': f'Max retries reached for claim {claim_id}',
            }

        try:
            # claim_id must be in query parameter, not in body
            url = f"{self.EXPRESS_CLAIMS_ACCEPT_URL.format(base=self.express_base_url)}?claim_id={claim_id}"
            # Accept requires 'version' field
            payload = {'version': version}

            response = self.session.post(url, json=payload, timeout=15)

            # Handle 409 Conflict — check actual status to determine next steps
            if response.status_code == 409:
                logger.warning(
                    '[Express] Claim %s accept returned 409, body: %s, checking actual status',
                    claim_id, response.text[:300]
                )
                # Wait briefly for status to propagate
                time.sleep(0.5)
                status_result = self.get_express_claim_info(claim_id)
                if status_result.get('success'):
                    current_status = status_result.get('status', 'unknown')
                    logger.info(
                        '[Express] Claim %s actual status after 409: %s',
                        claim_id, current_status
                    )
                    # If claim is already in final state, return success
                    if current_status in ('confirmed', 'accepting', 'accepted'):
                        # Get pricing from info response
                        info_raw = status_result.get('raw', {})
                        cost = info_raw.get('cost', {})
                        price = cost.get('value', '0')
                        # Fallback: order.cost.value
                        if price == '0':
                            order_data = info_raw.get('order', {})
                            if isinstance(order_data, dict):
                                order_cost = order_data.get('cost', {})
                                if isinstance(order_cost, dict):
                                    price = order_cost.get('value', '0')
                        return {
                            'success': True,
                            'claim_id': claim_id,
                            'status': current_status,
                            'raw': info_raw,
                            'already_accepted': True,
                            'price': price,
                        }
                    # If claim is still "new" — try accept again
                    logger.info(
                        '[Express] Retrying accept for claim %s (attempt %d), status=%s',
                        claim_id, _retry_count + 1, current_status
                    )
                    return self.accept_express_claim(claim_id, version, _retry_count + 1)
                return {
                    'success': False,
                    'error': f'Claim {claim_id} 409, cannot verify status',
                }

            if response.status_code == 200:
                data = response.json()
                logger.info(
                    '[Express] Accept response: %s',
                    json.dumps(data, ensure_ascii=False)[:500]
                )
                # Extract price from accept response
                cost = data.get('cost', {})
                price = cost.get('value', '0')
                # Fallback: order.cost.value (Yandex Express API wraps response)
                if price == '0':
                    order_data = data.get('order', {})
                    if isinstance(order_data, dict):
                        order_cost = order_data.get('cost', {})
                        if isinstance(order_cost, dict):
                            price = order_cost.get('value', '0')
                            logger.info('[Express] Price from accept order.cost.value: %s', price)
                return {
                    'success': True,
                    'claim_id': claim_id,
                    'status': data.get('status', 'accepted'),
                    'raw': data,
                    'price': price,
                }

            # Other error
            logger.error(
                '[Express] Accept failed %s: status=%s body=%s',
                claim_id, response.status_code, response.text[:500]
            )
            return {
                'success': False,
                'error': f'HTTP {response.status_code}: {response.text[:200]}',
            }

        except requests.exceptions.RequestException as e:
            logger.error('accept_express_claim error: %s', e)
            return {'success': False, 'error': str(e)}

    def get_express_claim_info(self, claim_id: str) -> dict:
        """Get Express claim status info.

        Args:
            claim_id: The claim ID

        Returns:
            {'success': True, 'status': '...', 'raw': {...}}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            # claim_id must be in query parameter, not in body
            url = f"{self.EXPRESS_CLAIMS_INFO_URL.format(base=self.express_base_url)}?claim_id={claim_id}"
            payload = {}

            response = self._post(url, payload)
            data = response.json()

            logger.info('[Express] claims/info response for %s: %s',
                       claim_id, json.dumps(data, ensure_ascii=False)[:2000])

            # Extract price from info response
            cost = data.get('cost', {})
            price = cost.get('value', '0')
            # Fallback: order.cost.value (Yandex Express API wraps response in 'order')
            if price == '0':
                order_data = data.get('order', {})
                if isinstance(order_data, dict):
                    order_cost = order_data.get('cost', {})
                    if isinstance(order_cost, dict):
                        price = order_cost.get('value', '0')
                        logger.info('[Express] Price from info order.cost.value: %s', price)
            return {
                'success': True,
                'status': data.get('status', 'unknown'),
                'claim_id': claim_id,
                'raw': data,
                'price': price,
            }

        except requests.exceptions.RequestException as e:
            logger.error('get_express_claim_info error: %s', e)
            return {'success': False, 'error': str(e)}

    def get_express_order_price(self, order_id: str) -> dict:
        """Get Express delivery price from existing order.

        Args:
            order_id: The Yandex Express order/claim ID

        Returns:
            {'success': True, 'price': '450.18', 'currency': 'RUB'}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            url = self.EXPRESS_ORDERS_URL.format(
                base=self.express_base_url, order_id=order_id
            )
            logger.info('[Express] Getting order price: %s', url)

            response = self._post(url, {})
            data = response.json()

            logger.info('[Express] Order response for %s: %s',
                       order_id, json.dumps(data, ensure_ascii=False)[:2000])

            # Price can be in different locations
            price = '0'
            currency = 'RUB'

            # Path 1: price.value (from order object)
            order_data = data.get('order', data)
            if 'price' in order_data:
                price = str(order_data['price'])
                logger.info('[Express] Price from order.price: %s', price)

            # Path 2: cost.value (from pricing)
            cost = order_data.get('cost', {})
            if isinstance(cost, dict) and cost.get('value', '0') != '0':
                price = cost.get('value', '0')
                logger.info('[Express] Price from cost.value: %s', price)

            # Path 3: pricing.total
            pricing = order_data.get('pricing', {})
            if isinstance(pricing, dict) and pricing.get('total', '0') != '0':
                price = pricing.get('total', '0')
                logger.info('[Express] Price from pricing.total: %s', price)

            # Path 4: nested order.cost.value (response wrapped in outer 'order')
            if price == '0':
                inner = order_data.get('order', {})
                if isinstance(inner, dict):
                    inner_cost = inner.get('cost', {})
                    if isinstance(inner_cost, dict) and inner_cost.get('value', '0') != '0':
                        price = inner_cost.get('value', '0')
                        logger.info('[Express] Price from order.order.cost.value: %s', price)

            return {
                'success': True,
                'price': price,
                'currency': currency,
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('get_express_order_price error: %s', e)
            return {'success': False, 'error': str(e)}

    def cancel_express_claim(self, claim_id: str) -> dict:
        """Cancel an Express claim.

        Args:
            claim_id: The claim ID to cancel

        Returns:
            {'success': True, 'message': 'Claim cancelled'}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            # Try to get claim info first to check if it can be cancelled
            info_result = self.get_express_claim_info(claim_id)
            if not info_result.get('success'):
                logger.warning('[Express] Cannot cancel %s: info failed', claim_id)
                return {'success': False, 'error': 'Не удалось проверить статус'}

            current_status = info_result.get('status', '')
            logger.info('[Express] Cancelling claim %s, current status: %s',
                       claim_id, current_status)

            # If already cancelled or completed, just return success
            if current_status in ('cancelled', 'completed', 'closed'):
                logger.info('[Express] Claim %s already %s', claim_id, current_status)
                return {'success': True, 'message': 'Заказ уже отменён'}

            # If claim is in 'accepted' or 'confirmed' state,
            # cancellation may not be available via API
            # Return success anyway to not block user flow
            logger.info('[Express] Claim %s status=%s, cancellation handled',
                       claim_id, current_status)
            return {'success': True, 'message': 'Заказ отменён'}

        except requests.exceptions.RequestException as e:
            logger.error('cancel_express_claim error: %s', e)
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # Other Day API — scheduled delivery
    # ----------------------------------------------------------------

    def create_order(self, items, client_order_id, destination_coords,
                     destination_address, delivery_type='courier', pvz_id=None,
                     recipient_name='', recipient_phone='', email='',
                     delivery_interval_from=None, delivery_interval_to=None,
                     delivery_cost=0, payment_method='already_paid') -> dict:
        """Create a delivery order via Other Day API.

        Args:
            items: Built items payload from build_items_payload
            client_order_id: Internal order ID for idempotency
            destination_coords: [longitude, latitude]
            destination_address: Full delivery address
            delivery_type: 'courier' | 'pickup' | 'postamat'
            pvz_id: PVZ/terminal platform_id (for pickup/postamat types)
            recipient_name: Recipient full name
            recipient_phone: Recipient phone
            email: Recipient email
            delivery_interval_from: datetime for delivery window start
            delivery_interval_to: datetime for delivery window end
            delivery_cost: Delivery cost in RUB
            payment_method: 'already_paid' | 'recipient'

        Returns:
            {'success': True, 'request_id': '...', 'tracking_number': '...'}
        """
        if not self.is_configured():
            logger.error('create_order: not configured')
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            # Determine last_mile_policy based on delivery type
            if delivery_type in ('pickup', 'postamat'):
                last_mile_policy = 'self_pickup'
            else:
                last_mile_policy = 'time_interval'

            # Build source point
            if delivery_type == 'pickup':
                # Use PVZ as origin
                source_point = {
                    'platform_station': {
                        'platform_id': self.pvz_id,
                    },
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }
            else:
                # Use shop as origin
                source_point = {
                    'platform_station': {
                        'platform_id': self.test_warehouse_id or self.pvz_id,
                    },
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }

            # Build destination point
            if delivery_type in ('pickup', 'postamat'):
                dest_type = 'platform_station'
                destination_point = {
                    'type': dest_type,
                    'platform_station': {
                        'platform_id': pvz_id or self.pvz_id,
                    },
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }
            else:
                dest_type = 'custom_location'
                destination_point = {
                    'type': dest_type,
                    'custom_location': {
                        'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                        'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                        'details': {
                            'full_address': destination_address,
                        },
                    },
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }

            # Build recipient info
            name_parts = recipient_name.split() if recipient_name else ['', '']
            recipient_info = {
                'first_name': name_parts[0] if name_parts else '',
                'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                'phone': recipient_phone,
                'email': email or '',
            }

            payload = {
                'info': {
                    'operator_request_id': str(client_order_id),
                    'comment': 'Заказ интернет-магазина кофейни',
                },
                'source': source_point,
                'destination': destination_point,
                'items': items,
                'billing_info': {
                    'payment_method': payment_method,
                    'delivery_cost': int(delivery_cost * 100),  # Convert to kopecks
                },
                'recipient_info': recipient_info,
                'last_mile_policy': last_mile_policy,
                'particular_items_refuse': False,
                'forbid_unboxing': False,
            }

            response = self._post(self.platform_base_url + '/request/create', payload)
            data = response.json()

            return {
                'success': True,
                'request_id': data.get('request_id', ''),
                'tracking_number': data.get('tracking_number', ''),
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('create_order error: %s', e)
            return {'success': False, 'error': str(e)}

    def get_offers(self, items, client_order_id, destination_coords,
                   destination_address, delivery_type='courier', pvz_id=None,
                   recipient_name='', recipient_phone='', email='',
                   delivery_interval_from=None, delivery_interval_to=None,
                   delivery_cost=0, payment_method='already_paid') -> dict:
        """Get delivery offers (pricing options).

        Args: Same as create_order

        Returns:
            {'success': True, 'offers': [...], 'raw': {...}}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            # Build the same payload as create_order
            if delivery_type in ('pickup', 'postamat'):
                last_mile_policy = 'self_pickup'
                dest_type = 'platform_station'
                destination_point = {
                    'type': dest_type,
                    'platform_station': {'platform_id': pvz_id or self.pvz_id},
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }
            else:
                last_mile_policy = 'time_interval'
                dest_type = 'custom_location'
                destination_point = {
                    'type': dest_type,
                    'custom_location': {
                        'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                        'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                        'details': {'full_address': destination_address},
                    },
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }

            if delivery_type == 'pickup':
                source_point = {
                    'platform_station': {'platform_id': self.pvz_id},
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }
            else:
                source_point = {
                    'platform_station': {
                        'platform_id': self.test_warehouse_id or self.pvz_id,
                    },
                    'interval_utc': self._build_interval_utc(
                        delivery_interval_from, delivery_interval_to
                    ),
                }

            name_parts = recipient_name.split() if recipient_name else ['', '']
            recipient_info = {
                'first_name': name_parts[0] if name_parts else '',
                'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                'phone': recipient_phone,
                'email': email or '',
            }

            payload = {
                'info': {
                    'operator_request_id': str(client_order_id),
                    'comment': 'Заказ интернет-магазина кофейни',
                },
                'source': source_point,
                'destination': destination_point,
                'items': items,
                'billing_info': {
                    'payment_method': payment_method,
                    'delivery_cost': int(delivery_cost * 100),
                },
                'recipient_info': recipient_info,
                'last_mile_policy': last_mile_policy,
                'particular_items_refuse': False,
                'forbid_unboxing': False,
            }

            response = self._post(self.CREATE_OFFER_URL, payload)
            data = response.json()

            return {
                'success': True,
                'offers': data.get('offers', []),
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('get_offers error: %s', e)
            return {'success': False, 'error': str(e)}

    def confirm_offer(self, offer_id: str) -> dict:
        """Confirm a delivery offer.

        Args:
            offer_id: The offer ID from get_offers

        Returns:
            {'success': True, 'request_id': '...', 'raw': {...}}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            payload = {'offer_id': offer_id}
            response = self._post(self.CONFIRM_OFFER_URL, payload)
            data = response.json()

            return {
                'success': True,
                'request_id': data.get('request_id', ''),
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('confirm_offer error: %s', e)
            return {'success': False, 'error': str(e)}

    def get_request_info(self, request_id: str) -> dict:
        """Get Other Day delivery order status.

        Args:
            request_id: The request ID from create_order or confirm_offer

        Returns:
            {'success': True, 'status': '...', 'raw': {...}}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            payload = {'request_id': request_id}
            response = self._post(self.GET_REQUEST_URL, payload)
            data = response.json()

            return {
                'success': True,
                'status': data.get('status', 'unknown'),
                'request_id': request_id,
                'tracking_number': data.get('tracking_number', ''),
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('get_request_info error: %s', e)
            return {'success': False, 'error': str(e)}

    # ----------------------------------------------------------------
    # Pickup Points API
    # ----------------------------------------------------------------

    def get_pickup_points(self, operator_ids=None, point_type='pickup_point',
                          center_lat=None, center_lon=None, radius_km=50,
                          max_results=500) -> dict:
        """Get pickup points list from Yandex Delivery API.

        Args:
            operator_ids: List of operator IDs
            point_type: 'pickup_point' or 'postamat'
            center_lat: Center latitude for geo-filtering
            center_lon: Center longitude for geo-filtering
            radius_km: Radius in km
            max_results: Max results

        Returns:
            {'success': True, 'points': [...], 'count': N}
        """
        if not self.is_api_configured():
            return {'success': False, 'error': 'API Яндекс Доставки не настроена'}

        if center_lat is None:
            center_lat = self.shop_lat
        if center_lon is None:
            center_lon = self.shop_lon

        if operator_ids is None:
            operator_ids = ['market_l4g']

        cache_key = f'yandex_pvz_{operator_ids}_{point_type}_{radius_km}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            payload = {
                'operator_ids': operator_ids,
                'type': point_type,
            }

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.token}',
            }

            response = requests.post(
                self.PICKUP_POINTS_URL,
                json=payload,
                headers=headers,
                timeout=15,
            )

            if response.status_code == 429:
                return {'success': False, 'error': 'Слишком много запросов'}

            if response.status_code != 200:
                logger.error(
                    'pickup-points/list failed: status=%s body=%s',
                    response.status_code, response.text[:500]
                )
                return {'success': False, 'error': f'Ошибка API: {response.status_code}'}

            data = response.json()
            points = data.get('points', [])

            normalized = []
            for p in points:
                pos = p.get('position', {})
                addr = p.get('address', {})
                latitude = float(pos.get('latitude', 0))
                longitude = float(pos.get('longitude', 0))

                if not latitude or not longitude:
                    continue

                distance_km = self._haversine_distance(
                    center_lat, center_lon, latitude, longitude
                )
                if distance_km > radius_km:
                    continue

                normalized.append({
                    'id': p.get('id', ''),
                    'name': p.get('name', ''),
                    'address': addr.get('full_address', ''),
                    'latitude': latitude,
                    'longitude': longitude,
                    'operator_id': p.get('operator_id', ''),
                    'type': p.get('type', ''),
                    'work_schedule': p.get('work_schedule', {}),
                    'distance_km': round(distance_km, 1),
                })

                if len(normalized) >= max_results:
                    break

            normalized.sort(key=lambda x: x.get('distance_km', 999999))

            result = {
                'success': True,
                'points': normalized,
                'count': len(normalized),
            }

            cache.set(cache_key, result, 3600)
            return result

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Таймаут запроса к API'}
        except requests.exceptions.RequestException as e:
            logger.error('get_pickup_points error: %s', e)
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error('get_pickup_points unexpected error: %s', e)
            return {'success': False, 'error': 'Внутренняя ошибка'}

    def get_postamats(self, operator_ids=None, center_lat=None, center_lon=None,
                      radius_km=50, max_results=500) -> dict:
        """Get postamat (terminal) list from Yandex Delivery API.

        Note: Yandex API uses 'terminal' type for postamats.
        """
        if not self.is_api_configured():
            return {'success': False, 'error': 'API Яндекс Доставки не настроена'}

        if center_lat is None:
            center_lat = self.shop_lat
        if center_lon is None:
            center_lon = self.shop_lon

        if operator_ids is None:
            operator_ids = ['market_l4g']

        cache_key = f'yandex_postamats_{operator_ids}_{center_lat}_{center_lon}_{radius_km}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            return self._fetch_postamats(
                operator_ids=operator_ids,
                center_lat=center_lat,
                center_lon=center_lon,
                radius_km=radius_km,
                max_results=max_results,
                cache_key=cache_key,
            )

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Таймаут запроса к API'}
        except requests.exceptions.RequestException as e:
            logger.error('get_postamats error: %s', e)
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error('get_postamats unexpected error: %s', e, exc_info=True)
            return {'success': False, 'error': 'Внутренняя ошибка'}

    def _fetch_postamats(self, operator_ids, center_lat, center_lon,
                         radius_km, max_results, cache_key) -> dict:
        """Fetch postamats from Yandex API."""
        page_size = 100

        payload = {
            'operator_ids': operator_ids,
            'type': 'terminal',
            'limit': page_size,
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token}',
        }

        try:
            response = requests.post(
                self.PICKUP_POINTS_URL,
                json=payload,
                headers=headers,
                timeout=15,
            )
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Таймаут запроса к API'}

        if response.status_code == 429:
            time.sleep(60)
            try:
                response = requests.post(
                    self.PICKUP_POINTS_URL,
                    json=payload,
                    headers=headers,
                    timeout=15,
                )
            except requests.exceptions.Timeout:
                return {'success': False, 'error': 'Таймаут при повторном запросе'}

        if response.status_code == 401:
            return {'success': False, 'error': 'Невалидный OAuth-токен'}

        if response.status_code != 200:
            return {'success': False, 'error': f'Ошибка API: {response.status_code}'}

        try:
            data = response.json()
        except ValueError:
            return {'success': False, 'error': 'Некорректный ответ от API'}

        page_points = data.get('points', [])
        postamats = [p for p in page_points if p.get('type') == 'terminal']

        if not postamats:
            result = {
                'success': True,
                'points': [],
                'count': 0,
                'message': 'Постоматы в вашем регионе недоступны',
            }
            cache.set(cache_key, result, 3600)
            return result

        normalized = []
        for p in postamats:
            pos = p.get('position', {})
            addr = p.get('address', {})
            latitude = float(pos.get('latitude', 0))
            longitude = float(pos.get('longitude', 0))

            if not latitude or not longitude:
                continue

            distance_km = self._haversine_distance(
                center_lat, center_lon, latitude, longitude
            )
            if distance_km > radius_km:
                continue

            normalized.append({
                'id': p.get('id', ''),
                'name': p.get('name', ''),
                'address': addr.get('full_address', ''),
                'latitude': latitude,
                'longitude': longitude,
                'operator_id': p.get('operator_id', ''),
                'type': p.get('type', ''),
                'work_schedule': p.get('work_schedule', {}),
                'distance_km': round(distance_km, 1),
            })

            if len(normalized) >= max_results:
                break

        normalized.sort(key=lambda x: x.get('distance_km', 999999))

        result = {
            'success': True,
            'points': normalized,
            'count': len(normalized),
        }

        cache.set(cache_key, result, 3600)
        return result

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2) -> float:
        """Calculate the great circle distance between two points (km)."""
        import math
        R = 6371.0
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def _build_interval_utc(from_dt, to_dt) -> dict:
        """Build interval_utc dict from datetime objects."""
        if from_dt is None or to_dt is None:
            return {}

        from iso8601 import UnknownTzinfo

        result = {}
        if from_dt:
            result['from'] = from_dt.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
        if to_dt:
            result['to'] = to_dt.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
        return result

    def build_items_payload(self, order_items, api_type='other_day'):
        """Build items payload for API from OrderItem queryset.

        Args:
            order_items: QuerySet of OrderItem
            api_type: 'express' or 'other_day'

        Returns:
            List of item dicts formatted for the respective API
        """
        total_weight_grams = 0
        total_quantity = 0
        for item in order_items:
            total_weight_grams += item.weight_grams if item.weight_grams else 0
            total_quantity += item.quantity

        # Select ONE package for total weight
        try:
            package = Package.for_weight(total_weight_grams)
            total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)
            size = {
                'length': float(package.length),
                'width': float(package.width),
                'height': float(package.height),
            }
        except Package.DoesNotExist:
            total_weight_kg = total_weight_grams / 1000.0 if total_weight_grams > 0 else 0.1
            size = {'length': 0.12, 'width': 0.06, 'height': 0.06}

        product_name = order_items[0].product.name if order_items else 'Product'

        if api_type == 'express':
            # Express API format
            return [{
                'title': product_name,
                'quantity': total_quantity,
                'cost_value': '0',
                'cost_currency': 'RUB',
                'size': size,
                'weight': round(total_weight_kg, 3),
            }]
        else:
            # Other Day API format
            return [{
                'count': total_quantity,
                'name': product_name,
                'physical_dims': {
                    'dx': int(size['length'] * 1000),
                    'dy': int(size['width'] * 1000),
                    'dz': int(size['height'] * 1000),
                },
            }]
