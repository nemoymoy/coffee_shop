"""Yandex Geocoder service — reverse geocoding & address autocomplete."""
import hashlib
import logging
import requests as http_requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class YandexGeocoderService:
    """Service for Yandex Geocoder API (maps.yandex.ru/geocode-maps)."""

    GEOCODE_URL = 'https://geocode-maps.yandex.ru/1.x/'
    CACHE_TTL = 300  # 5 minutes

    def __init__(self, api_key=None):
        self.api_key = api_key or getattr(settings, 'YANDEX_GEOCODER_API_KEY', '') or \
                       getattr(settings, 'YANDEX_MAPS_API_KEY', '')
        self._session = http_requests.Session()
        self._session.headers.update({'Accept': 'application/json'})

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def geocode(self, query: str, results: int = 10) -> dict:
        """
        Forward geocoding: address string → coordinates.

        Args:
            query: Address string (e.g. 'Самара ул Революционная 3')
            results: Number of results to return (default 10).

        Returns:
            {
                'success': True,
                'features': [
                    {'text': '...', 'coords': [lon, lat]},
                    ...
                ],
                'rate_limited': False,
                'api_error': False,
            }
        """
        if not query or not query.strip():
            return {'success': False, 'error': 'Запрос пустой'}

        if not self.is_configured():
            return {'success': False, 'error': 'API ключ не настроен'}

        # Cache for 5 minutes
        cache_key = f'geocode_{hashlib.md5(query.strip().encode()).hexdigest()}'
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            params = {
                'apikey': self.api_key,
                'geocode': query.strip(),
                'format': 'json',
                'lang': 'ru_RU',
                'results': results,
            }

            response = self._session.get(self.GEOCODE_URL, params=params, timeout=5)

            if response.status_code == 429:
                logger.warning('Geocoder rate limited for query: %s', query)
                result = {
                    'success': True,
                    'results': [],
                    'features': [],
                    'rate_limited': True,
                }
                return result

            if response.status_code != 200:
                logger.warning('Geocoder API error: %s for query: %s', response.status_code, query)
                return {
                    'success': True,
                    'results': [],
                    'features': [],
                    'api_error': True,
                }

            return self._parse_geocode_response(response.json(), cache_key)

        except http_requests.exceptions.Timeout:
            logger.error('Geocoder timeout for query: %s', query)
            return {'success': False, 'error': 'Таймаут запроса'}
        except Exception as e:
            logger.error('Geocoder error: %s', e)
            return {'success': False, 'error': str(e)}

    def geocode_first(self, query: str) -> dict:
        """
        Forward geocoding returning only the best match.

        Returns:
            {'success': True, 'coords': [lon, lat], 'text': 'formatted address'}
            or
            {'success': False, 'error': '...'}
        """
        result = self.geocode(query, results=1)
        if not result.get('success'):
            return result

        features = result.get('features', [])
        if not features:
            return {'success': False, 'error': 'Адрес не найден'}

        feature = features[0]
        coords = feature.get('coords')
        if not coords or len(coords) < 2:
            return {'success': False, 'error': 'Адрес без координат'}

        return {
            'success': True,
            'coords': coords,
            'text': feature.get('text', query),
        }

    def reverse_geocode(self, coords: list, kind: str = 'house') -> dict:
        """
        Reverse geocoding: coordinates → address string.

        Args:
            coords: [longitude, latitude]
            kind: GeoObject kind (default 'house').

        Returns:
            {'success': True, 'address': '...', 'coords': [lon, lat]}
        """
        if not coords or len(coords) < 2:
            return {'success': False, 'error': 'Некорректные координаты'}

        if not self.is_configured():
            return {'success': False, 'error': 'API ключ не настроен'}

        try:
            params = {
                'apikey': self.api_key,
                'geocode': ','.join(str(c) for c in coords),
                'format': 'json',
                'lang': 'ru_RU',
                'results': 1,
                'kind': kind,
            }

            response = self._session.get(self.GEOCODE_URL, params=params, timeout=5)

            if response.status_code != 200:
                logger.warning('Reverse geocoder error: %s', response.status_code)
                return {'success': False, 'error': 'Ошибка геокодинга'}

            return self._parse_reverse_geocode(response.json(), coords)

        except http_requests.exceptions.Timeout:
            return {'success': False, 'error': 'Таймаут запроса'}
        except Exception as e:
            logger.error('Reverse geocoder error: %s', e)
            return {'success': False, 'error': str(e)}

    def parse_coords(self, coords_str: str) -> list:
        """
        Parse coordinate string 'lon,lat' to [lon, lat].

        Returns:
            [float, float] or None
        """
        if not coords_str:
            return None

        if isinstance(coords_str, list):
            try:
                return [float(coords_str[0]), float(coords_str[1])]
            except (ValueError, IndexError):
                return None

        try:
            parts = coords_str.split(',')
            if len(parts) != 2:
                return None
            return [float(parts[0].strip()), float(parts[1].strip())]
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_geocode_response(json_data: dict, cache_key: str) -> dict:
        """Parse geocoder API response into normalized format."""
        results = []
        features = []

        geo_object_collection = (
            json_data.get('response', {})
            .get('GeoObjectCollection', {})
        )
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
                    coords = pos.split()

            if text:
                results.append(text)
                features.append({'text': text, 'coords': coords})

        result_data = {
            'success': True,
            'results': results,
            'features': features,
        }

        # Cache for 5 minutes
        cache.set(cache_key, result_data, 300)
        return result_data

    @staticmethod
    def _parse_reverse_geocode(json_data: dict, original_coords: list) -> dict:
        """Parse reverse geocoder API response."""
        geo_object_collection = (
            json_data.get('response', {})
            .get('GeoObjectCollection', {})
        )
        feature_members = geo_object_collection.get('featureMember', [])

        if not feature_members:
            return {'success': False, 'error': 'Адрес не найден'}

        geo_object = feature_members[0].get('GeoObject', {})
        meta = geo_object.get('metaDataProperty', {}).get('GeocoderMetaData', {})
        address = meta.get('text', '')

        return {
            'success': True,
            'address': address,
            'coords': original_coords,
        }
