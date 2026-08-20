"""Yandex Delivery service integration."""
import requests
from django.conf import settings
from .yandex_oauth import YandexOAuth


class YandexDeliveryService:
    """Сервис для работы с Яндекс Доставкой."""

    DELIVERY_API = 'https://da.yandex.ru'

    def __init__(self, access_token: str = None):
        oauth = YandexOAuth()
        self.access_token = access_token or oauth.access_token
        self.yandex_account_id = oauth.get_yandex_account()

    def is_configured(self) -> bool:
        """Проверка, что сервис настроен."""
        return bool(self.access_token and self.yandex_account_id)

    def calculate_price(self, address: dict) -> dict:
        """
        Расчёт стоимости и ETA доставки.

        Args:
            address: {'city': 'moscow', 'street': 'ул. Примерная', 'house': '1'}

        Returns:
            {'success': True, 'price': 299, 'eta': '30-45 мин'}
            или {'success': False, 'error': '...'}
        """
        if not self.is_configured():
            return {
                'success': True,
                'price': 299,
                'eta': '30-45 мин',
                'mock': True,
            }

        try:
            payload = {
                'yandex_account_id': self.yandex_account_id,
                'city': address.get('city', 'moscow'),
                'from_address': {
                    'city': settings.YANDEX_FROM_CITY or 'moscow',
                    'street': settings.YANDEX_FROM_STREET or '',
                    'house': settings.YANDEX_FROM_HOUSE or '',
                    'apartment': settings.YANDEX_FROM_APT or '',
                },
                'to_address': {
                    'city': address.get('city', 'moscow'),
                    'street': address.get('street', ''),
                    'house': address.get('house', ''),
                    'apartment': address.get('apartment', ''),
                },
            }

            response = requests.post(
                f'{self.DELIVERY_API}/v1/delivery/calculate',
                json=payload,
                headers={'Authorization': f'OAuth {self.access_token}'},
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            return {
                'success': True,
                'price': data.get('price', 0),
                'eta': data.get('eta', '---'),
            }

        except requests.RequestException as e:
            return {
                'success': False,
                'error': str(e),
            }

    def create_delivery_order(self, order_id: int, address: dict, packages: list = None) -> dict:
        """
        Создаёт заказ на доставку.

        Args:
            order_id: ID заказа в системе
            address: {'street': '...', 'house': '...', 'apartment': '...'}
            packages: [{'weight': 0.5, 'length': 30, 'width': 20, 'height': 10}]

        Returns:
            {'success': True, 'tracking_number': '...'}
            или {'success': False, 'error': '...'}
        """
        if not self.is_configured():
            return {
                'success': True,
                'tracking_number': f'YA-DEV-{order_id}',
                'mock': True,
            }

        try:
            payload = {
                'yandex_account_id': self.yandex_account_id,
                'order_id': str(order_id),
                'address': address,
                'packages': packages or [
                    {'weight': 0.5, 'length': 30, 'width': 20, 'height': 10}
                ],
            }

            response = requests.post(
                f'{self.DELIVERY_API}/v1/delivery/order',
                json=payload,
                headers={'Authorization': f'OAuth {self.access_token}'},
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            return {
                'success': True,
                'tracking_number': data.get('tracking_number', ''),
                'yandex_order_id': data.get('id', ''),
                'eta': data.get('eta'),
            }

        except requests.RequestException as e:
            return {
                'success': False,
                'error': str(e),
            }

    def get_delivery_status(self, tracking_number: str) -> dict:
        """Получает статус доставки по трек-номеру."""
        if not self.is_configured():
            return {
                'success': True,
                'status': 'in_transit',
                'mock': True,
            }

        try:
            response = requests.get(
                f'{self.DELIVERY_API}/v1/delivery/{tracking_number}/status',
                headers={'Authorization': f'OAuth {self.access_token}'},
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            return {
                'success': True,
                'status': data.get('status', 'unknown'),
                'history': data.get('history', []),
            }

        except requests.RequestException as e:
            return {
                'success': False,
                'error': str(e),
            }

    def get_pvz_locations(self, city: str = None, pvz_type: str = 'pvz') -> dict:
        """
        Получает список пунктов выдачи и постоматов.
        
        Args:
            city: Город (по умолчанию из настроек)
            pvz_type: 'pvz' или 'postomat'
            
        Returns:
            {'success': True, 'points': [...]} или {'success': False, 'error': '...'}
        """
        if not self.is_configured():
            return {
                'success': True,
                'points': [],
                'mock': True,
                'error': 'Yandex Delivery not configured',
            }

        try:
            # API Яндекс Доставки для получения ПВЗ
            # Документация: https://yandex.ru/dev/delivery/docs/ru/reference/pickup-points
            city = city or getattr(settings, 'YANDEX_FROM_CITY', 'samara')
            
            payload = {
                'yandex_account_id': self.yandex_account_id,
                'city': city,
                'type': pvz_type,  # 'pvz' или 'postomat'
            }

            response = requests.post(
                f'{self.DELIVERY_API}/v1/pickup-points/list',
                json=payload,
                headers={'Authorization': f'OAuth {self.access_token}'},
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            points = []
            
            # Парсим ответ API Яндекс Доставки
            for pp in data.get('pickup_points', []):
                # Проверяем тип пункта
                if pvz_type == 'postomat':
                    # Фильтруем только постоматы
                    if not pp.get('is_postomat', False):
                        continue
                else:
                    # Фильтруем только ПВЗ
                    if pp.get('is_postomat', False):
                        continue
                
                points.append({
                    'id': pp.get('id'),
                    'name': pp.get('name', ''),
                    'address': pp.get('address', ''),
                    'coordinates': pp.get('coordinates'),  # [lat, lon]
                    'type': 'postomat' if pp.get('is_postomat') else 'pvz',
                    'working_hours': pp.get('working_hours', ''),
                    'phone': pp.get('phone', ''),
                })

            return {
                'success': True,
                'points': points,
                'mock': False,
            }

        except requests.RequestException as e:
            return {
                'success': False,
                'points': [],
                'error': str(e),
            }
