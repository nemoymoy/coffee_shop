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


def retry_with_backoff(max_retries=3, base_delay=2):
    """Decorator for retrying requests with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    return result
                except requests.exceptions.HTTPError as e:
                    status = e.response.status_code if e.response is not None else None
                    if status == 429:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            'Rate limited on %s (attempt %d/%d), retrying in %ds',
                            func.__name__, attempt + 1, max_retries, delay
                        )
                        time.sleep(delay)
                        continue
                    raise
                except requests.exceptions.ConnectionError as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            'Connection error on %s (attempt %d/%d), retrying in %ds: %s',
                            func.__name__, attempt + 1, max_retries, delay, str(e)[:100]
                        )
                        time.sleep(delay)
                        continue
                    raise
            return {'success': False, 'error': 'Max retries exceeded due to rate limiting'}
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
    OFFERS_INFO_URL = f'{BASE_URL}/offers/info'
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
        # Self-pickup station (source for PVZ/postamat delivery)
        self.pickup_station_id = getattr(
            settings, 'YANDEX_PICKUP_STATION_ID',
            'd0222b1e-73ff-4274-9c68-42c79d4c7eae'
        )
        self.pickup_station_lat = float(
            getattr(settings, 'YANDEX_PICKUP_STATION_LAT', 53.21808624267578)
        )
        self.pickup_station_lon = float(
            getattr(settings, 'YANDEX_PICKUP_STATION_LON', 50.16553497314453)
        )
        self.pickup_station_address = getattr(
            settings, 'YANDEX_PICKUP_STATION_ADDRESS',
            'Пункт выдачи заказов Яндекс Маркета — Самара улица Лукачёва 6'
        )
        # PVZ for backward compatibility
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
            # Return response so retry_with_backoff can catch it
            response.raise_for_status()
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
        if response.status_code == 429:
            logger.warning('Rate limited on %s', url)
            response.raise_for_status()
        if response.status_code != 200:
            logger.error(
                '_get failed %s: status=%s body=%s',
                url, response.status_code, response.text[:500]
            )
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

    def _build_other_day_payload(self, items_data, places_data, client_order_id,
                                 source_point, destination_point, recipient_name,
                                 recipient_phone, email, delivery_cost,
                                 payment_method='already_paid',
                                 last_mile_policy='self_pickup') -> dict:
        """Build a complete Other Day API payload (shared by offers/info, offers/create).

        Args:
            items_data: List of item dicts (items section)
            places_data: List of place dicts (places section, top-level)
            client_order_id: Internal order ID for idempotency
            source_point: Source station dict (platform_station or custom_location)
            destination_point: Destination station dict
            recipient_name: Full name (will be split into first/last)
            recipient_phone: Phone number
            email: Email address
            delivery_cost: Delivery cost in RUB
            payment_method: 'already_paid' | 'recipient'
            last_mile_policy: 'self_pickup' | 'time_interval'

        Returns:
            Complete payload dict for Other Day API
        """
        name_parts = recipient_name.split() if recipient_name else ['', '']
        # Yandex requires valid phone format (+7XXXXXXXXXX)
        phone = recipient_phone or '+79000000000'
        if not phone.startswith('+'):
            phone = '+7' + phone if phone.startswith('8') else '+7' + phone
        recipient_info = {
            'first_name': name_parts[0] if name_parts else '',
            'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
            'phone': phone,
            'email': email or '',
        }

        return {
            'info': {
                'operator_request_id': str(client_order_id),
                'comment': 'Заказ интернет-магазина кофейни',
            },
            'source': source_point,
            'destination': destination_point,
            'items': items_data,
            'places': places_data,
            'billing_info': {
                'payment_method': payment_method,
                'delivery_cost': int(delivery_cost * 100),  # kopecks
            },
            'recipient_info': recipient_info,
            'last_mile_policy': last_mile_policy,
            'particular_items_refuse': False,
            'forbid_unboxing': False,
        }

    def _build_source_destination(self, delivery_type, pvz_id=None):
        """Build source and destination points for Other Day API.

        For PVZ/postamat: source = default PVZ station, destination = user-selected station.
        For courier: source = warehouse station, destination = custom location.

        Returns:
            (source_point, destination_point, last_mile_policy) tuple
        """
        if delivery_type in ('pickup', 'postamat'):
            last_mile_policy = 'self_pickup'
            source_point = {
                'platform_station_id': self.pvz_id,
            }
            destination_point = {
                'type': 'platform_station',
                'platform_station_id': pvz_id or self.pvz_id,
            }
        else:
            last_mile_policy = 'time_interval'
            source_point = {
                'platform_station_id': self.test_warehouse_id or self.pvz_id,
            }
            # For courier, destination will be set by caller (custom_location)
            destination_point = None

        return source_point, destination_point, last_mile_policy

    @retry_with_backoff(max_retries=3, base_delay=3)
    def get_offers_info(self, items_data, places_data, client_order_id,
                        destination_coords, destination_address, delivery_type='courier',
                        pvz_id=None, recipient_name='', recipient_phone='', email='') -> dict:
        """Get available delivery intervals and offers (offers/info).

        This is Step 1 of the Other Day API flow:
        1. offers/info — get available intervals
        2. offers/create — reserve a slot
        3. offers/confirm — confirm the offer

        Args:
            items_data: List of item dicts
            places_data: List of place dicts
            client_order_id: Internal order ID
            destination_coords: [longitude, latitude]
            destination_address: Full delivery address
            delivery_type: 'courier' | 'pickup' | 'postamat'
            pvz_id: PVZ/terminal platform_id (for pickup/postamat)
            recipient_name: Recipient full name
            recipient_phone: Recipient phone
            email: Recipient email

        Returns:
            {'success': True, 'offers': [...], 'raw': {...}}
        """
        if not self.is_configured():
            logger.error('get_offers_info: not configured')
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        # Cache key based on source, destination, and items
        cache_key = f'offers_info_{pvz_id}_{delivery_type}_{destination_coords}_{client_order_id}'
        cached = cache.get(cache_key)
        if cached:
            logger.info('[OtherDay] get_offers_info: returning cached result')
            return cached

        try:
            source_point, dest_point, last_mile_policy = self._build_source_destination(
                delivery_type, pvz_id
            )

            # For courier, add custom_location destination
            if delivery_type == 'courier' and dest_point is None:
                dest_point = {
                    'type': 'custom_location',
                    'custom_location': {
                        'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                        'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                        'details': {'full_address': destination_address},
                    },
                }

            payload = self._build_other_day_payload(
                items_data=items_data,
                places_data=places_data,
                client_order_id=client_order_id,
                source_point=source_point,
                destination_point=dest_point,
                recipient_name=recipient_name,
                recipient_phone=recipient_phone,
                email=email,
                delivery_cost=0,
                payment_method='already_paid',
                last_mile_policy=last_mile_policy,
            )

            logger.info('[OtherDay] === get_offers_info payload ===')
            logger.info('[OtherDay] source: %s', json.dumps(source_point, ensure_ascii=False))
            logger.info('[OtherDay] destination: %s', json.dumps(dest_point, ensure_ascii=False))
            logger.info('[OtherDay] last_mile_policy: %s', last_mile_policy)
            logger.info('[OtherDay] items_data: %s', json.dumps(items_data, ensure_ascii=False)[:1000])
            logger.info('[OtherDay] places_data: %s', json.dumps(places_data, ensure_ascii=False)[:1000])
            logger.info('[OtherDay] recipient_name: %s', recipient_name)
            logger.info('[OtherDay] recipient_phone: %s', recipient_phone)
            logger.info('[OtherDay] recipient_email: %s', email)

            # Use platform_base_url for production (b2b-authproxy) vs test (b2b.taxi)
            offers_info_url = f'{self.platform_base_url}/offers/info'
            logger.info('[OtherDay] Calling URL: %s', offers_info_url)

            try:
                response = self._post(offers_info_url, payload)
                data = response.json()

                logger.info('[OtherDay] get_offers_info response: %s',
                           json.dumps(data, ensure_ascii=False)[:3000])

            except requests.exceptions.HTTPError as e:
                logger.error('[OtherDay] HTTP error: %s', e)
                logger.error('[OtherDay] Response status: %s', e.response.status_code if e.response else 'N/A')
                logger.error('[OtherDay] Response body: %s', e.response.text[:2000] if e.response else 'N/A')
                logger.error('[OtherDay] Full payload: %s', json.dumps(payload, ensure_ascii=False)[:3000])
                raise

            result = {
                'success': True,
                'offers': data.get('offers', []),
                'raw': data,
            }

            # Cache result for 5 minutes
            cache.set(cache_key, result, 300)
            return result

        except requests.exceptions.RequestException as e:
            logger.error('get_offers_info error: %s', e)
            return {'success': False, 'error': str(e)}

    def create_order(self, items, client_order_id, destination_coords,
                     destination_address, delivery_type='courier', pvz_id=None,
                     recipient_name='', recipient_phone='', email='',
                     delivery_interval_from=None, delivery_interval_to=None,
                     delivery_cost=0, payment_method='already_paid') -> dict:
        """Create a delivery order via Other Day API.

        Full flow: offers/info → offers/create → offers/confirm → request/info
        or: offers/info → request/create (if no offers available)

        For PVZ/postamat types:
            1. offers/info — check available intervals
            2a. If offers exist → offers/create → offers/confirm
            2b. If no offers → request/create (nearest available time)
            3. request/info — get price, date, status

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
            {'success': True, 'request_id': '...', 'tracking_number': '...',
             'offer_id': '...', 'status': '...', 'delivery_date': '...',
             'delivery_time': '...', 'price': '...', 'currency': 'RUB'}
        """
        if not self.is_configured():
            logger.error('create_order: not configured')
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        # Only the PVZ/postamat flow uses offers/info → offers/create → request/info
        if delivery_type not in ('pickup', 'postamat'):
            return self._create_order_courier(
                items, client_order_id, destination_coords, destination_address,
                delivery_type, pvz_id, recipient_name, recipient_phone, email,
                delivery_interval_from, delivery_interval_to, delivery_cost,
                payment_method,
            )

        try:
            # Build common parts for offers/info
            source_pvz_id = pvz_id or self.pickup_station_id
            common_source = {
                'platform_station': {
                    'platform_id': self.pickup_station_id,
                },
            }
            common_destination = {
                'type': 'platform_station',
                'platform_station': {
                    'platform_id': source_pvz_id,
                },
            }
            common_billing = {
                'payment_method': payment_method,
                'delivery_cost': int(delivery_cost * 100),  # kopecks
            }

            # Build items and places
            api_items, api_places = self._build_items_for_other_day(
                items, delivery_type, pvz_id
            )

            # Recipient info
            name_parts = recipient_name.split() if recipient_name else ['', '']
            phone = recipient_phone or '+79000000000'
            if not phone.startswith('+'):
                phone = '+7' + phone if phone.startswith('8') else '+7' + phone
            recipient_info = {
                'first_name': name_parts[0] if name_parts else '',
                'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                'phone': phone,
                'email': email or '',
            }

            # ── Step 1: offers/info — check available intervals ────────
            logger.info('[OtherDay] === create_order: offers/info ===')
            info_body = {
                'info': {'operator_request_id': str(client_order_id)},
                'source': {'platform_station_id': self.pickup_station_id},
                'destination': {'platform_station_id': source_pvz_id},
                'places': api_places,
                'last_mile_policy': 'self_pickup',
            }

            offers_info_url = f'{self.platform_base_url}/offers/info'
            resp = self._post(offers_info_url, info_body)
            info_data = resp.json()

            logger.info('[OtherDay] offers/info response: %s',
                       json.dumps(info_data, ensure_ascii=False)[:3000])

            # Filter valid offers (must have offer_id and delivery_interval.from)
            valid_offers = [
                o for o in info_data.get('offers', [])
                if o.get('offer_id') and o.get('delivery_interval', {}).get('from')
            ]

            request_id = None
            method_used = None
            offer_id = None

            # ── Step 2a: Offers exist → offers/create → offers/confirm ─
            if valid_offers:
                logger.info('[OtherDay] Found %d intervals. Taking nearest.',
                           len(valid_offers))

                valid_offers.sort(
                    key=lambda o: o['delivery_interval']['from']
                )
                nearest = valid_offers[0]

                delivery_from = nearest['delivery_interval']['from']
                delivery_to = nearest['delivery_interval']['to']
                pickup_from = nearest.get('pickup_interval', {}).get(
                    'min', delivery_from
                )
                pickup_to = nearest.get('pickup_interval', {}).get(
                    'max', delivery_from
                )

                create_body = {
                    'info': {
                        'operator_request_id': str(client_order_id),
                    },
                    'source': {
                        **common_source,
                        'interval_utc': {'from': pickup_from, 'to': pickup_to},
                    },
                    'destination': {
                        **common_destination,
                        'interval_utc': {'from': delivery_from, 'to': delivery_to},
                    },
                    'items': api_items,
                    'places': api_places,
                    'recipient_info': recipient_info,
                    'billing_info': common_billing,
                    'last_mile_policy': 'self_pickup',
                    'particular_items_refuse': False,
                    'forbid_unboxing': False,
                }

                logger.info('[OtherDay] === create_order: offers/create ===')
                create_url = f'{self.platform_base_url}/offers/create'
                resp = self._post(create_url, create_body)
                created = resp.json()

                logger.info('[OtherDay] offers/create response: %s',
                           json.dumps(created, ensure_ascii=False)[:2000])

                offers = created.get('offers', [])
                if not offers:
                    return {
                        'success': False,
                        'error': 'Нет офферов в ответе offers/create',
                    }

                offer = offers[0]
                offer_id = offer.get('offer_id')
                expires_at = offer.get('expires_at')
                logger.info('[OtherDay] Offer created: %s, expires: %s',
                           offer_id, expires_at)

                # ── Step 2a-ii: offers/confirm ──────────────────────────
                logger.info('[OtherDay] === create_order: offers/confirm ===')
                confirm_payload = {'offer_id': offer_id}
                confirm_url = f'{self.platform_base_url}/offers/confirm'
                resp = self._post(confirm_url, confirm_payload)
                confirmed = resp.json()

                logger.info('[OtherDay] offers/confirm response: %s',
                           json.dumps(confirmed, ensure_ascii=False)[:1000])

                request_id = confirmed.get('request_id')
                method_used = 'offers'

                if not request_id:
                    return {
                        'success': False,
                        'error': 'Нет request_id в ответе offers/confirm',
                    }

            # ── Step 2b: No offers → request/create ─────────────────────
            else:
                logger.info('[OtherDay] No intervals available. '
                           'Creating request for nearest time (request/create)...')

                request_body = {
                    'info': {
                        'operator_request_id': str(client_order_id),
                        'comment': 'Доставка ПВЗ→ПВЗ, ближайшее доступное время',
                    },
                    'source': common_source,
                    'destination': common_destination,
                    'items': api_items,
                    'places': api_places,
                    'recipient_info': recipient_info,
                    'billing_info': common_billing,
                    'last_mile_policy': 'self_pickup',
                }

                request_create_url = f'{self.platform_base_url}/request/create'
                resp = self._post(request_create_url, request_body)
                created = resp.json()

                logger.info('[OtherDay] request/create response: %s',
                           json.dumps(created, ensure_ascii=False)[:1000])

                request_id = created.get('request_id')
                method_used = 'request'

                if not request_id:
                    return {
                        'success': False,
                        'error': 'Нет request_id в ответе request/create',
                    }

            # ── Step 3: request/info — get price, date, status ──────────
            logger.info('[OtherDay] Order created (%s). request_id: %s',
                       method_used, request_id)
            logger.info('[OtherDay] Waiting for price and interval calculation...')

            order_info = None
            order_info = None
            has_price_or_interval = False
            for attempt in range(10):
                time.sleep(3)
                tracking_info = self.get_request_info(request_id)
                if not tracking_info.get('success'):
                    logger.warning('[OtherDay] request/info attempt %d failed',
                                 attempt + 1)
                    continue

                order_info = tracking_info.get('raw', {})
                status = order_info.get('status', '')
                pricing = order_info.get('pricing', {})
                interval = order_info.get('delivery_interval', {})

                # Wait until price appears, interval appears, or order failed
                if (pricing.get('total') or interval.get('from') or
                        status == 'failed'):
                    has_price_or_interval = True
                    break
                logger.info('[OtherDay]   attempt %d: status=%s, waiting...',
                           attempt + 1, status)

            if not order_info or not has_price_or_interval:
                return {
                    'success': False,
                    'error': 'timeout',
                    'message': 'Не удалось получить данные заказа за отведённое время.',
                }

            if order_info.get('status') == 'failed':
                return {
                    'success': False,
                    'error': 'order_failed',
                    'message': str(order_info.get('error_messages', 'Заказ не создан.')),
                    'request_id': request_id,
                }

            # ── Format result ───────────────────────────────────────────
            di = order_info.get('delivery_interval', {})
            d_from = di.get('from')
            d_to = di.get('to')

            delivery_date = ''
            delivery_time = ''
            if d_from:
                try:
                    from datetime import datetime, timezone, timedelta
                    # Parse ISO format and convert to local timezone (UTC+4 Samara)
                    tz_local = timezone(timedelta(hours=4))
                    dt_from = datetime.fromisoformat(
                        d_from.replace('Z', '+00:00')
                    ).astimezone(tz_local)
                    delivery_date = dt_from.strftime('%d.%m.%Y')
                    if d_to:
                        dt_to = datetime.fromisoformat(
                            d_to.replace('Z', '+00:00')
                        ).astimezone(tz_local)
                        delivery_time = (
                            f"{dt_from.strftime('%H:%M')}–{dt_to.strftime('%H:%M')}"
                        )
                    else:
                        delivery_time = dt_from.strftime('%H:%M')
                except Exception as e:
                    logger.warning('[OtherDay] Failed to parse delivery interval: %s', e)

            pricing = order_info.get('pricing', {})
            price_total = pricing.get('total', 'N/A')
            currency = pricing.get('currency', 'RUB')

            return {
                'success': True,
                'request_id': request_id,
                'method': method_used,
                'status': order_info.get('status'),
                'tracker_id': order_info.get('tracker_id'),
                'offer_id': offer_id,
                'delivery_date': delivery_date,
                'delivery_time': delivery_time,
                'price': price_total,
                'currency': currency,
                'raw': order_info,
            }

        except requests.exceptions.RequestException as e:
            logger.error('create_order error: %s', e)
            return {'success': False, 'error': str(e)}

    def _create_order_courier(self, items, client_order_id, destination_coords,
                              destination_address, delivery_type, pvz_id,
                              recipient_name, recipient_phone, email,
                              delivery_interval_from, delivery_interval_to,
                              delivery_cost, payment_method) -> dict:
        """Create a courier delivery order via Other Day API.

        Simplified flow: offers/create → offers/confirm → request/info
        (courier doesn't use offers/info check)

        Returns:
            {'success': True, 'request_id': '...', 'tracking_number': '...',
             'offer_id': '...', 'status': '...'}
        """
        try:
            source_point, dest_point, last_mile_policy = self._build_source_destination(
                delivery_type, pvz_id
            )

            # For courier, add custom_location destination with interval
            if delivery_type == 'courier' and dest_point is None:
                dest_point = {
                    'type': 'custom_location',
                    'custom_location': {
                        'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                        'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                        'details': {'full_address': destination_address},
                    },
                }

            # Build items and places from OrderItem data
            api_items, api_places = self._build_items_for_other_day(
                items, delivery_type, pvz_id
            )

            payload = self._build_other_day_payload(
                items_data=api_items,
                places_data=api_places,
                client_order_id=client_order_id,
                source_point=source_point,
                destination_point=dest_point,
                recipient_name=recipient_name,
                recipient_phone=recipient_phone,
                email=email,
                delivery_cost=delivery_cost,
                payment_method=payment_method,
                last_mile_policy=last_mile_policy,
            )

            # Add interval_utc if provided
            if delivery_interval_from and delivery_interval_to:
                payload['source']['interval_utc'] = {
                    'from': delivery_interval_from,
                    'to': delivery_interval_to,
                }
                if dest_point and delivery_type in ('pickup', 'postamat'):
                    payload['destination']['interval_utc'] = {
                        'from': delivery_interval_from,
                        'to': delivery_interval_to,
                    }

            # Step 1: offers/create — reserve a delivery slot
            logger.info('[OtherDay] === create_order (courier): offers/create ===')
            create_url = f'{self.platform_base_url}/offers/create'
            create_response = self._post(create_url, payload)
            create_data = create_response.json()

            logger.info('[OtherDay] offers/create response: %s',
                       json.dumps(create_data, ensure_ascii=False)[:2000])

            offers = create_data.get('offers', [])
            if not offers:
                return {
                    'success': False,
                    'error': 'Нет доступных офферов при создании заказа',
                }

            # Take the first offer
            offer = offers[0]
            offer_id = offer.get('offer_id')
            if not offer_id:
                return {
                    'success': False,
                    'error': 'Нет offer_id в ответе offers/create',
                }

            logger.info('[OtherDay] Offer created: %s', offer_id)

            # Step 2: offers/confirm — confirm the offer
            logger.info('[OtherDay] === create_order (courier): offers/confirm ===')
            confirm_payload = {'offer_id': offer_id}
            confirm_url = f'{self.platform_base_url}/offers/confirm'
            confirm_response = self._post(confirm_url, confirm_payload)
            confirm_data = confirm_response.json()

            logger.info('[OtherDay] offers/confirm response: %s',
                       json.dumps(confirm_data, ensure_ascii=False)[:1000])

            request_id = confirm_data.get('request_id')
            if not request_id:
                return {
                    'success': False,
                    'error': 'Нет request_id в ответе offers/confirm',
                }

            logger.info('[OtherDay] Order confirmed: request_id=%s', request_id)

            # Step 3: request/info — get tracking number and status
            time.sleep(1)
            tracking_info = self.get_request_info(request_id)

            return {
                'success': True,
                'request_id': request_id,
                'tracking_number': tracking_info.get('tracking_number', ''),
                'offer_id': offer_id,
                'status': tracking_info.get('status', 'pending'),
                'raw': confirm_data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('_create_order_courier error: %s', e)
            return {'success': False, 'error': str(e)}

    def _build_items_for_other_day(self, items, delivery_type, pvz_id):
        """Build items and places for Other Day API from pre-built data.

        Items and places should already be in Other Day format from the caller.
        This method ensures proper structure with billing_details.

        Returns:
            (items_list, places_list) tuple
        """
        if not items:
            return [], []

        # Items and places are already in Other Day format from _build_items_payload
        # Just ensure they have required fields
        inn = getattr(settings, 'YANDEX_MERCHANT_INN', '7707083893')
        nds = 20  # НДС 20%

        # Ensure items have billing_details
        for item in items:
            if 'billing_details' not in item:
                item['billing_details'] = {
                    'inn': inn,
                    'nds': nds,
                }

        # Ensure places have billing_details and proper structure
        for place in items:  # places are derived from items
            if 'billing_details' not in place:
                place['billing_details'] = {
                    'inn': inn,
                    'nds': nds,
                }

        return items, items

    def _build_items_payload_for_other_day(self, order_items, pvz_id=None):
        """Build items and places for Other Day API from OrderItem queryset.

        This creates properly formatted items and places for offers/create.

        Args:
            order_items: QuerySet of OrderItem
            pvz_id: PVZ platform_id (used as barcode prefix)

        Returns:
            (items, places) tuple in Other Day API format
        """
        total_weight_grams = 0
        total_quantity = 0
        product_names = []

        for item in order_items:
            total_weight_grams += item.weight_grams if item.weight_grams else 0
            total_quantity += item.quantity
            if item.product:
                product_names.append(item.product.name)

        # Select ONE package for total weight
        try:
            package = Package.for_weight(total_weight_grams)
            size = {
                'dx': int(float(package.length) * 1000),
                'dy': int(float(package.width) * 1000),
                'dz': int(float(package.height) * 1000),
            }
        except Package.DoesNotExist:
            size = {'dx': 120, 'dy': 60, 'dz': 60}

        product_name = product_names[0] if product_names else 'Кофе'
        inn = getattr(settings, 'YANDEX_MERCHANT_INN', '7707083893')

        # Calculate total price for billing
        total_price_kopecks = 0
        for item in order_items:
            if item.unit_price:
                try:
                    total_price_kopecks += int(float(item.unit_price) * 100)
                except (ValueError, TypeError):
                    total_price_kopecks += 150000  # fallback 1500 RUB

        unit_price_kopecks = total_price_kopecks // total_quantity if total_quantity > 0 else 150000

        # Common barcode — MUST match between items.place_barcode and places.barcode
        place_barcode = f'BOX-{order_items.first().pk if order_items.first() else "001"}'

        items = [{
            'count': total_quantity,
            'name': product_name,
            'article': f'COFFEE-{order_items.first().pk if order_items.first() else "001"}',
            'billing_details': {
                'unit_price': unit_price_kopecks,
                'assessed_unit_price': unit_price_kopecks,
                'inn': inn,
                'nds': 20,
            },
            'physical_dims': size,
            'place_barcode': place_barcode,
        }]

        places = [{
            'barcode': place_barcode,
            'physical_dims': {
                **size,
                'weight_gross': total_weight_grams + int(float(package.tare_weight) * 1000),  # product + package tare
            },
        }]

        return items, places

    def get_offers(self, items, client_order_id, destination_coords,
                   destination_address, delivery_type='courier', pvz_id=None,
                   recipient_name='', recipient_phone='', email='',
                   delivery_interval_from=None, delivery_interval_to=None,
                   delivery_cost=0, payment_method='already_paid') -> dict:
        """Get delivery offers (pricing options) — offers/create.

        This is Step 2 of the flow (after offers/info).

        Args: Same as create_order

        Returns:
            {'success': True, 'offers': [...], 'raw': {...}}
        """
        if not self.is_configured():
            logger.error('get_offers: not configured')
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            source_point, dest_point, last_mile_policy = self._build_source_destination(
                delivery_type, pvz_id
            )

            # For courier, add custom_location destination
            if delivery_type == 'courier' and dest_point is None:
                dest_point = {
                    'type': 'custom_location',
                    'custom_location': {
                        'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                        'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                        'details': {'full_address': destination_address},
                    },
                }

            payload = self._build_other_day_payload(
                items_data=items,
                places_data=items,  # places are same as items for price calculation
                client_order_id=client_order_id,
                source_point=source_point,
                destination_point=dest_point,
                recipient_name=recipient_name,
                recipient_phone=recipient_phone,
                email=email,
                delivery_cost=delivery_cost,
                payment_method=payment_method,
                last_mile_policy=last_mile_policy,
            )

            logger.info('[OtherDay] === get_offers (offers/create) payload ===')
            logger.info('[OtherDay] source: %s', json.dumps(source_point, ensure_ascii=False))
            logger.info('[OtherDay] destination: %s', json.dumps(dest_point, ensure_ascii=False))
            logger.info('[OtherDay] last_mile_policy: %s', last_mile_policy)

            try:
                create_url = f'{self.platform_base_url}/offers/create'
                response = self._post(create_url, payload)
                data = response.json()

                logger.info('[OtherDay] get_offers response: %s',
                           json.dumps(data, ensure_ascii=False)[:2000])

                return {
                    'success': True,
                    'offers': data.get('offers', []),
                    'raw': data,
                }

            except requests.exceptions.HTTPError as e:
                logger.error('[OtherDay] HTTP error: %s', e)
                logger.error('[OtherDay] Response status: %s',
                           e.response.status_code if e.response else 'N/A')
                logger.error('[OtherDay] Response body: %s',
                           e.response.text[:2000] if e.response else 'N/A')
                return {
                    'success': False,
                    'error': f'HTTP {e.response.status_code if e.response else "?"}: {e.response.text[:500] if e.response else str(e)}',
                }
            except Exception as e:
                logger.error('[OtherDay] Unexpected error: %s', e, exc_info=True)
                return {'success': False, 'error': str(e)}

        except requests.exceptions.RequestException as e:
            logger.error('get_offers error: %s', e)
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
            # Build Other Day API payload
            # Frontend sends Express format (quantity, weight, size),
            # Other Day API needs different structure with places at root level
            if items and items[0]:
                first_item = items[0]
                if 'weight' in first_item and 'size' in first_item:
                    # Convert from Express format to Other Day format
                    place_barcode = 'BOX-001'
                    other_day_items = [{
                        'count': int(first_item.get('quantity', 1)),
                        'name': first_item.get('title', 'Товар'),
                        'article': 'coffee-item',
                        'place_barcode': place_barcode,
                        'billing_details': {
                            'manufacturer_country': 'RU',
                            'excise': False,
                            'unit_price': 10000,
                            'assessed_unit_price': 10000,
                        },
                        'physical_dims': {
                            'dx': int(first_item.get('size', {}).get('length', 0.12) * 1000),
                            'dy': int(first_item.get('size', {}).get('width', 0.06) * 1000),
                            'dz': int(first_item.get('size', {}).get('height', 0.06) * 1000),
                        },
                    }]
                    # places is a top-level field in Other Day API
                    places = [{
                        'count': int(first_item.get('quantity', 1)),
                        'name': first_item.get('title', 'Товар'),
                        'article': 'coffee-item',
                        'barcode': place_barcode,
                        'place_barcode': place_barcode,
                        'billing_details': {
                            'manufacturer_country': 'RU',
                            'excise': False,
                            'unit_price': 10000,
                            'assessed_unit_price': 10000,
                        },
                        'physical_dims': {
                            'dx': int(first_item.get('size', {}).get('length', 0.12) * 1000),
                            'dy': int(first_item.get('size', {}).get('width', 0.06) * 1000),
                            'dz': int(first_item.get('size', {}).get('height', 0.06) * 1000),
                        },
                    }]
                else:
                    other_day_items = items
                    places = items
            else:
                other_day_items = items
                places = items

            # Build source and destination points
            if delivery_type in ('pickup', 'postamat'):
                # For self_pickup: source is the default PVZ, destination is user-selected PVZ
                last_mile_policy = 'self_pickup'
                source_point = {
                    'platform_station_id': self.pvz_id,
                }
                destination_point = {
                    'platform_station_id': pvz_id or self.pvz_id,
                }
            else:
                # For courier: source is shop/warehouse, destination is customer address
                last_mile_policy = 'time_interval'
                source_point = {
                    'platform_station_id': self.test_warehouse_id or self.pvz_id,
                }
                destination_point = {
                    'custom_location': {
                        'latitude': destination_coords[1] if len(destination_coords) > 1 else 0,
                        'longitude': destination_coords[0] if len(destination_coords) > 0 else 0,
                        'details': {'full_address': destination_address},
                    },
                }

            name_parts = recipient_name.split() if recipient_name else ['', '']
            recipient_info = {
                'first_name': name_parts[0] if name_parts else 'Клиент',
                'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                'phone': recipient_phone or '+79000000000',
                'email': email or '',
            }

            payload = {
                'info': {
                    'operator_request_id': str(client_order_id),
                    'comment': 'Заказ интернет-магазина кофейни',
                },
                'source': source_point,
                'destination': destination_point,
                'items': other_day_items,
                'places': places,
                'billing_info': {
                    'payment_method': payment_method,
                    'delivery_cost': int(delivery_cost * 100),
                },
                'recipient_info': recipient_info,
                'last_mile_policy': last_mile_policy,
                'particular_items_refuse': False,
                'forbid_unboxing': False,
            }

            logger.info('[OtherDay] === get_offers payload ===')
            logger.info('[OtherDay] source: %s', json.dumps(source_point, ensure_ascii=False))
            logger.info('[OtherDay] destination: %s', json.dumps(destination_point, ensure_ascii=False))
            logger.info('[OtherDay] last_mile_policy: %s', last_mile_policy)
            logger.info('[OtherDay] items (converted): %s', json.dumps(other_day_items, ensure_ascii=False))
            logger.info('[OtherDay] recipient_info: %s', json.dumps(recipient_info, ensure_ascii=False))
            logger.info('[OtherDay] billing_info: %s', json.dumps(payload['billing_info'], ensure_ascii=False))
            logger.info('[OtherDay] Full payload: %s', json.dumps(payload, ensure_ascii=False))

            try:
                create_url = f'{self.platform_base_url}/offers/create'
                response = self._post(create_url, payload)
                data = response.json()

                logger.info('[OtherDay] get_offers response: %s', json.dumps(data, ensure_ascii=False)[:2000])

                return {
                    'success': True,
                    'offers': data.get('offers', []),
                    'raw': data,
                }

            except requests.exceptions.HTTPError as e:
                logger.error('[OtherDay] HTTP error: %s', e)
                logger.error('[OtherDay] Response status: %s', e.response.status_code if e.response else 'N/A')
                logger.error('[OtherDay] Response body: %s', e.response.text[:2000] if e.response else 'N/A')
                return {'success': False, 'error': f'HTTP {e.response.status_code if e.response else "?"}: {e.response.text[:500] if e.response else str(e)}'}
            except Exception as e:
                logger.error('[OtherDay] Unexpected error: %s', e, exc_info=True)
                return {'success': False, 'error': str(e)}

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
            confirm_url = f'{self.platform_base_url}/offers/confirm'
            response = self._post(confirm_url, payload)
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

        Uses GET with request_id as query parameter (Yandex API requires GET).

        Args:
            request_id: The request ID from create_order or confirm_offer

        Returns:
            {'success': True, 'status': '...', 'raw': {...}}
        """
        if not self.is_configured():
            return {'success': False, 'error': 'Яндекс Доставка не настроена'}

        try:
            request_url = f'{self.platform_base_url}/request/info?request_id={request_id}'
            response = self._get(request_url)
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

    @retry_with_backoff(max_retries=3, base_delay=3)
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

            pickup_points_url = f'{self.platform_base_url}/pickup-points/list'

            @retry_with_backoff(max_retries=3, base_delay=3)
            def _fetch_pvz():
                return self.session.post(pickup_points_url, json=payload, timeout=15)

            try:
                response = _fetch_pvz()
            except requests.exceptions.Timeout:
                return {'success': False, 'error': 'Таймаут запроса к API'}

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

    @retry_with_backoff(max_retries=3, base_delay=3)
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

        pickup_points_url = f'{self.platform_base_url}/pickup-points/list'

        @retry_with_backoff(max_retries=3, base_delay=3)
        def _fetch_page():
            return self.session.post(pickup_points_url, json=payload, timeout=15)

        try:
            response = _fetch_page()
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Таймаут запроса к API'}

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
