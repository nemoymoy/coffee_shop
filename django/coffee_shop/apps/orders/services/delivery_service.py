"""Yandex Cargo Delivery service integration (b2b/cargo/integration/v2)."""
import logging
import time
import requests
from functools import wraps
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Taxi class constants for Yandex Cargo
TAXI_CLASS_CHOICES = {
    'courier': 'courier',  # пеший/велокурьер, до 10 кг
    'express': 'express',  # автокурьер, до 20 кг
    'cargo': 'cargo',      # грузовой, до 300 кг
}
DEFAULT_TAXI_CLASS = 'courier'

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 90  # Leave 10 requests margin


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
    """Service for Yandex Cargo API (b2b/cargo/integration/v2)."""

    CHECK_PRICE_URL = 'https://b2b-authproxy.taxi.yandex.net/b2b/cargo/integration/v2/check-price'
    CREATE_ORDER_URL = 'https://b2b-authproxy.taxi.yandex.net/b2b/cargo/integration/v2/orders'
    GET_ORDER_URL = 'https://b2b-authproxy.taxi.yandex.net/b2b/cargo/integration/v2/orders/{order_id}'

    def __init__(self):
        self.token = getattr(settings, 'YANDEX_DELIVERY_TOKEN', '')
        self.shop_lat = getattr(settings, 'YANDEX_SHOP_LAT', 53.1960)
        self.shop_lon = getattr(settings, 'YANDEX_SHOP_LON', 49.3782)
        self.shop_address = getattr(settings, 'YANDEX_SHOP_ADDRESS', 'Самара, ул. Революционная, д. 3')

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Language': 'ru_RU',
        })

        # Configure retry for HTTPAdapter
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('https://', adapter)

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
            logger.warning('is_configured: token prefix invalid: %s', self.token[:20])
            return False
        return True

    def _post(self, url, payload):
        """HTTP POST with rate limiting."""
        response = self.session.post(url, json=payload, timeout=15)
        if response.status_code == 429:
            logger.warning('Rate limited on %s', url)
            raise requests.exceptions.HTTPError(f'429 Too Many Requests')
        if response.status_code != 200:
            logger.error('_post failed %s: status=%s body=%s', url, response.status_code, response.text[:500])
            response.raise_for_status()
        return response

    @rate_limited(max_requests_per_minute=90)
    def _get(self, url):
        """HTTP GET with rate limiting."""
        response = self.session.get(url, timeout=15)
        response.raise_for_status()
        return response

    def calculate_price(self, items, destination_coords, destination_address, delivery_type='courier') -> dict:
        """
        Calculate delivery price via check-price API.

        Args:
            items: [{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}}]
            destination_coords: [longitude, latitude]
            destination_address: string address
            delivery_type: 'courier' | 'pickup'

        Returns:
            {'success': True, 'price': '350.00', 'currency_rules': {...}, 'delivery_days': 2}
        """
        if not self.is_configured():
            logger.error('calculate_price: not configured')
            return {
                'success': False,
                'error': 'Яндекс Доставка не настроена',
            }

        # Check cache first (5 min TTL)
        cache_key = f'yandex_delivery_price_{hash(frozenset(str(items).items() if isinstance(items, dict) else []))}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            taxi_class = DEFAULT_TAXI_CLASS
            requirements = {
                'delivery_type': 'courier' if delivery_type == 'courier' else 'pickup',
                'taxi_class': taxi_class,
            }

            route_points = [
                {
                    'id': 1,
                    'coordinates': [self.shop_lon, self.shop_lat],
                    'fullname': self.shop_address,
                },
                {
                    'id': 2,
                    'coordinates': destination_coords,
                    'fullname': destination_address,
                },
            ]

            payload = {
                'items': items,
                'route_points': route_points,
                'requirements': requirements,
            }

            logger.info('check-price payload: %s', payload)
            logger.info('check-price authorization: %s', self.session.headers.get('Authorization', 'MISSING')[:30] + '...')

            response = self._post(self.CHECK_PRICE_URL, payload)
            data = response.json()
            logger.info('check-price response: %s', data)

            result = {
                'success': True,
                'price': str(data.get('price', 0)),
                'currency_rules': data.get('currency_rules', {}),
                'delivery_days': data.get('delivery_days'),
                'raw': data,
            }

            # Cache for 5 minutes
            cache.set(cache_key, result, 300)
            return result

        except requests.exceptions.RequestException as e:
            logger.error('calculate_price error: %s', e)
            return {
                'success': False,
                'error': str(e),
            }

    def create_order(self, items, client_order_id, destination_coords, destination_address, delivery_type='courier', pvz_id=None) -> dict:
        """
        Create delivery order via Cargo API.

        Args:
            items: [{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}, 'title': 'Coffee 250g'}]
            client_order_id: internal order ID for status matching
            destination_coords: [longitude, latitude]
            destination_address: string address
            delivery_type: 'courier' | 'pickup'
            pvz_id: PVZ/terminal ID (for pickup type)

        Returns:
            {'success': True, 'order_id': '...', 'tracking_number': '...'}
        """
        if not self.is_configured():
            logger.error('create_order: not configured')
            return {
                'success': False,
                'error': 'Яндекс Доставка не настроена',
            }

        try:
            taxi_class = DEFAULT_TAXI_CLASS
            requirements = {
                'delivery_type': 'courier' if delivery_type == 'courier' else 'pickup',
                'taxi_class': taxi_class,
            }

            # Build route points
            route_points = [
                {
                    'id': 'shop-1',
                    'type': 'pickup',
                    'coordinates': [self.shop_lon, self.shop_lat],
                    'address': self.shop_address,
                },
            ]

            if delivery_type == 'courier':
                route_points.append({
                    'id': 'dropoff-1',
                    'type': 'dropoff',
                    'coordinates': destination_coords,
                    'address': destination_address,
                })
            else:
                pvz_point = {
                    'id': f'pvz-{pvz_id or "unknown"}',
                    'type': 'dropoff',
                    'coordinates': destination_coords,
                    'address': destination_address,
                }
                if pvz_id:
                    pvz_point['pvz_id'] = pvz_id
                route_points.append(pvz_point)

            payload = {
                'items': items,
                'route_points': route_points,
                'requirements': requirements,
                'client_order_id': str(client_order_id),
                'comment': 'Заказ интернет-магазина кофейни',
            }

            response = self._post(self.CREATE_ORDER_URL, payload)
            data = response.json()

            return {
                'success': True,
                'order_id': data.get('id', ''),
                'tracking_number': data.get('tracking_number', ''),
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('create_order error: %s', e)
            return {
                'success': False,
                'error': str(e),
            }

    def get_order_status(self, order_id: str) -> dict:
        """Get delivery order status."""
        if not self.is_configured():
            return {
                'success': False,
                'error': 'Яндекс Доставка не настроена',
            }

        try:
            url = self.GET_ORDER_URL.format(order_id=order_id)
            response = self._get(url)
            data = response.json()

            return {
                'success': True,
                'status': data.get('status', 'unknown'),
                'tracking_number': data.get('tracking_number', ''),
                'raw': data,
            }

        except requests.exceptions.RequestException as e:
            logger.error('get_order_status error: %s', e)
            return {
                'success': False,
                'error': str(e),
            }

    def build_items_payload(self, order_items):
        """
        Build items payload for API from OrderItem queryset.

        Args:
            order_items: QuerySet of OrderItem

        Returns:
            List of item dicts for API
        """
        items = []
        for item in order_items:
            weight_kg = item.weight_grams / 1000.0 if item.weight_grams else 0.5
            size = {}
            if item.package:
                size = {
                    'length': float(item.package.length),
                    'width': float(item.package.width),
                    'height': float(item.package.height),
                }
            else:
                # Default size for medium package
                size = {
                    'length': 0.20,
                    'width': 0.12,
                    'height': 0.12,
                }

            items.append({
                'quantity': item.quantity,
                'weight': round(weight_kg, 3),
                'size': size,
                'title': item.product.name if item.product else 'Product',
            })
        return items
