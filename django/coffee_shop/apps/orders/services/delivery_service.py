"""Yandex Cargo Delivery service integration (b2b/cargo/integration/v2)."""
import json
import logging
import time
import requests
from functools import wraps
from django.conf import settings
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Lazy import to avoid circular dependency
from coffee_shop.apps.orders.models import Package

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
        # YANDEX_DELIVERY_API_KEY — это тот же ключ, что и YANDEX_DELIVERY_TOKEN
        self.api_key = getattr(settings, 'YANDEX_DELIVERY_TOKEN', '')
        self.shop_lat = getattr(settings, 'YANDEX_SHOP_LAT', 53.216940239129094)
        self.shop_lon = getattr(settings, 'YANDEX_SHOP_LON', 50.162688008923745)
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

    def is_api_configured(self) -> bool:
        """Check if the pickup points API is configured."""
        if not self.token:
            logger.warning('is_api_configured: no token')
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

    # Pickup Points API URL
    PICKUP_POINTS_URL = 'https://b2b-authproxy.taxi.yandex.net/api/b2b/platform/pickup-points/list'

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2) -> float:
        """
        Calculate the great circle distance between two points on earth (km).
        Uses the Haversine formula.
        """
        import math
        R = 6371.0  # Earth radius in kilometers
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r
        a = math.sin(dlat / 2) ** 2 + \
            math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c



    def get_postamats(self, operator_ids=None, center_lat=None, center_lon=None,
                      radius_km=50, max_results=500) -> dict:
        """
        Get postamat (terminal) list from Yandex Delivery API.
        Запрашивает все точки оператора и фильтрует по type=terminal.

        Args:
            operator_ids: List of operator IDs (e.g. ['market_l4g']).
            center_lat: Center latitude for geo-filtering.
            center_lon: Center longitude for geo-filtering.
            radius_km: Radius in km for geo-filtering.
            max_results: Max number of points to return.

        Returns:
            {'success': True, 'points': [...], 'count': N}
        """
        if not self.is_api_configured():
            logger.warning('get_postamats: API not configured')
            return {
                'success': False,
                'error': 'API Яндекс Доставки не настроена',
            }

        if center_lat is None:
            center_lat = self.shop_lat
        if center_lon is None:
            center_lon = self.shop_lon

        if operator_ids is None:
            operator_ids = ['market_l4g']

        # Cache for 1 hour (postamat list changes rarely)
        cache_key = f'yandex_postamats_{operator_ids}_{center_lat}_{center_lon}_{radius_km}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            # Используем тот же URL, что и для pickup_points
            payload = {
                'operator_ids': operator_ids,
                'type': 'pickup_point',  # Запрашиваем все точки
            }

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
            }

            response = requests.post(
                self.PICKUP_POINTS_URL,
                json=payload,
                headers=headers,
                timeout=15,
            )

            if response.status_code == 429:
                logger.warning('Rate limited on pickup-points/list')
                return {
                    'success': False,
                    'error': 'Слишком много запросов. Попробуйте позже.',
                }

            if response.status_code != 200:
                logger.error('pickup-points/list failed: status=%s body=%s', response.status_code, response.text[:500])
                return {
                    'success': False,
                    'error': f'Ошибка API: {response.status_code}',
                }

            data = response.json()
            all_points = data.get('points', [])

            # Логируем типы точек
            types_count = {}
            for p in all_points:
                t = p.get('type', 'unknown')
                types_count[t] = types_count.get(t, 0) + 1
            logger.info('pickup-points types (all): %s', types_count)

            # Фильтруем только постоматы (type=terminal)
            postamats = [p for p in all_points if p.get('type') == 'terminal']
            logger.info('postamats found: %d', len(postamats))

            if not postamats:
                return {
                    'success': True,
                    'points': [],
                    'count': 0,
                    'message': 'Постоматы в вашем регионе недоступны',
                }

            # Geo-filter: only points within radius of the shop
            normalized = []
            for p in postamats:
                pos = p.get('position', {})
                addr = p.get('address', {})
                latitude = float(pos.get('latitude', 0))
                longitude = float(pos.get('longitude', 0))

                if not latitude or not longitude:
                    continue

                distance_km = self._haversine_distance(
                    center_lat, center_lon,
                    latitude, longitude
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

            # Sort by distance (closest first)
            normalized.sort(key=lambda x: x.get('distance_km', 999999))

            result = {
                'success': True,
                'points': normalized,
                'count': len(normalized),
            }

            # Cache for 1 hour
            cache.set(cache_key, result, 3600)
            return result

        except requests.exceptions.Timeout:
            logger.error('get_postamats: request timeout')
            return {
                'success': False,
                'error': 'Таймаут запроса к API',
            }
        except requests.exceptions.RequestException as e:
            logger.error('get_postamats error: %s', e)
            return {
                'success': False,
                'error': str(e),
            }
        except Exception as e:
            logger.error('get_postamats unexpected error: %s', e)
            return {
                'success': False,
                'error': 'Внутренняя ошибка',
            }

    def get_pickup_points(self, operator_ids=None, point_type='pickup_point',
                          center_lat=None, center_lon=None, radius_km=50, max_results=500) -> dict:
        """
        Get pickup points list from Yandex Delivery API.

        Args:
            operator_ids: List of operator IDs (e.g. ['market_l4g'] for Market PVZs).
                          If None, defaults to Market PVZs only.
            point_type: 'pickup_point' or 'postat'. Defaults to 'pickup_point'.
            center_lat: Center latitude for geo-filtering. Defaults to shop_lat.
            center_lon: Center longitude for geo-filtering. Defaults to shop_lon.
            radius_km: Radius in km for geo-filtering. Defaults to 50.
            max_results: Max number of points to return. Defaults to 500.

        Returns:
            {'success': True, 'points': [{'id': ..., 'name': ..., 'address': ..., 'position': {...}}, ...]}
        """
        if not self.is_api_configured():
            logger.warning('get_pickup_points: API not configured')
            return {
                'success': False,
                'error': 'API Яндекс Доставки не настроена',
            }

        # Defaults to shop coordinates for geo-filtering
        if center_lat is None:
            center_lat = self.shop_lat
        if center_lon is None:
            center_lon = self.shop_lon

        # Cache for 1 hour (PVZ list changes rarely)
        cache_key = f'yandex_pvz_{operator_ids or "market_l4g"}_{point_type}_{radius_km}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            if operator_ids is None:
                operator_ids = ['market_l4g']

            payload = {
                'operator_ids': operator_ids,
                'type': point_type,
            }

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
            }

            response = requests.post(
                self.PICKUP_POINTS_URL,
                json=payload,
                headers=headers,
                timeout=15,
            )

            if response.status_code == 429:
                logger.warning('Rate limited on pickup-points/list')
                return {
                    'success': False,
                    'error': 'Слишком много запросов. Попробуйте позже.',
                }

            if response.status_code != 200:
                logger.error('pickup-points/list failed: status=%s body=%s', response.status_code, response.text[:500])
                return {
                    'success': False,
                    'error': f'Ошибка API: {response.status_code}',
                }

            data = response.json()
            
            # Детальное логирование для отладки
            logger.info('pickup-points/list response: %s', json.dumps(data, ensure_ascii=False)[:1000])
            
            points = data.get('points', [])
            
            # Логируем типы точек
            types_count = {}
            for p in points:
                t = p.get('type', 'unknown')
                types_count[t] = types_count.get(t, 0) + 1
            logger.info('pickup-points types: %s', types_count)

            # Normalize point data for frontend
            normalized = []
            for p in points:
                pos = p.get('position', {})
                addr = p.get('address', {})
                latitude = float(pos.get('latitude', 0))
                longitude = float(pos.get('longitude', 0))

                if not latitude or not longitude:
                    continue

                # Geo-filter: only points within radius of the shop
                distance_km = self._haversine_distance(
                    center_lat, center_lon,
                    latitude, longitude
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

            # Sort by distance (closest first)
            normalized.sort(key=lambda x: x.get('distance_km', 999999))

            result = {
                'success': True,
                'points': normalized,
                'count': len(normalized),
            }

            # Cache for 1 hour
            cache.set(cache_key, result, 3600)
            return result

        except requests.exceptions.Timeout:
            logger.error('get_pickup_points: request timeout')
            return {
                'success': False,
                'error': 'Таймаут запроса к API',
            }
        except requests.exceptions.RequestException as e:
            logger.error('get_pickup_points error: %s', e)
            return {
                'success': False,
                'error': str(e),
            }
        except Exception as e:
            logger.error('get_pickup_points unexpected error: %s', e)
            return {
                'success': False,
                'error': 'Внутренняя ошибка',
            }

    def build_items_payload(self, order_items):
        """
        Build items payload for API from OrderItem queryset.
        Сначала суммирует вес всех товаров, затем выбирает ОДНУ тару для суммарного веса.
        """
        items = []
        
        # 1. Суммируем вес всех товаров
        total_weight_grams = 0
        total_quantity = 0
        for item in order_items:
            total_weight_grams += item.weight_grams if item.weight_grams else 0
            total_quantity += item.quantity
        
        # 2. Выбираем ОДНУ тару для суммарного веса
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
            size = {
                'length': 0.12,
                'width': 0.06,
                'height': 0.06,
            }
        
        items.append({
            'quantity': total_quantity,
            'weight': round(total_weight_kg, 3),
            'size': size,
            'title': order_items[0].product.name if order_items else 'Product',
        })
        return items
