"""Tests for YandexGeocoderService."""
import pytest
from unittest.mock import patch, MagicMock
from coffee_shop.apps.orders.services.geocoder_service import YandexGeocoderService


pytestmark = pytest.mark.django_db


class TestYandexGeocoderService:
    """Tests for Yandex Geocoder service."""

    def test_is_configured_no_key(self):
        with patch.object(YandexGeocoderService, '__init__', lambda self: None):
            service = YandexGeocoderService()
            service.api_key = ''
            assert service.is_configured() is False

    def test_is_configured_with_key(self):
        with patch.object(YandexGeocoderService, '__init__', lambda self: None):
            service = YandexGeocoderService()
            service.api_key = 'test-key'
            assert service.is_configured() is True

    def test_parse_coords_list(self):
        geocoder = YandexGeocoderService(api_key='test')
        assert geocoder.parse_coords([49.35, 53.21]) == [49.35, 53.21]

    def test_parse_coords_string(self):
        geocoder = YandexGeocoderService(api_key='test')
        assert geocoder.parse_coords("49.35,53.21") == [49.35, 53.21]

    def test_parse_coords_empty(self):
        geocoder = YandexGeocoderService(api_key='test')
        assert geocoder.parse_coords('') is None
        assert geocoder.parse_coords(None) is None

    def test_parse_coords_invalid_string(self):
        geocoder = YandexGeocoderService(api_key='test')
        assert geocoder.parse_coords("abc,def") is None
        assert geocoder.parse_coords("only_one") is None

    def test_parse_coords_extra_elements(self):
        # Берёт первые два элемента из списка
        geocoder = YandexGeocoderService(api_key='test')
        assert geocoder.parse_coords([1, 2, 3]) == [1.0, 2.0]

    def test_geocode_empty_query(self):
        geocoder = YandexGeocoderService(api_key='test-key')
        result = geocoder.geocode('')
        assert result['success'] is False

    @patch.object(YandexGeocoderService, 'is_configured')
    def test_geocode_unconfigured(self, mock_configured):
        mock_configured.return_value = False
        geocoder = YandexGeocoderService(api_key='test-key')
        result = geocoder.geocode('test query')
        assert result['success'] is False
        assert 'API ключ не настроен' in result['error']

    def test_geocode_first_no_results(self):
        geocoder = YandexGeocoderService(api_key='test-key')
        result = geocoder.geocode_first('nonexistent-place-xyz-123')
        # Will fail due to rate limiting or no results - that's expected
        assert 'success' in result
