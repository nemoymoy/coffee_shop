"""Yandex OAuth 2.0 service for Yandex Delivery integration."""
import os
import requests
from django.conf import settings


class YandexOAuth:
    """OAuth 2.0 client for Yandex Delivery authorization."""

    AUTH_URL = 'https://oauth.yandex.ru/authorize'
    TOKEN_URL = 'https://oauth.yandex.ru/token'
    YANDEX_HOST = 'api.yandex.ru/v1/yandex-account'

    CLIENT_ID = getattr(settings, 'YANDEX_DELIVERY_CLIENT_ID', '')
    CLIENT_SECRET = getattr(settings, 'YANDEX_DELIVERY_CLIENT_SECRET', '')

    def __init__(self):
        self.client_id = self.CLIENT_ID
        self.client_secret = self.CLIENT_SECRET
        self.access_token = None
        # Renamed from `self.refresh_token` to avoid shadowing the method name
        self._refresh_token = None

    def is_configured(self) -> bool:
        """Check if the OAuth service is properly configured."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str = '') -> str:
        """Generate the OAuth authorization URL."""
        params = {
            'client_id': self.client_id,
            'redirect_uri': getattr(
                settings, 'YANDEX_REDIRECT_URI',
                'http://localhost:8000/delivery/callback/'
            ),
            'response_type': 'code',
            'state': state,
        }
        separator = '?'
        url = self.AUTH_URL
        for key, value in params.items():
            url += f'{separator}{key}={value}'
            separator = '&'
        return url

    def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for an access token.

        Args:
            code: The authorization code received from Yandex.

        Returns:
            Dict with access_token, refresh_token, and optional error.
        """
        if not self.is_configured():
            # DEV-MODE: return fake tokens
            return {
                'access_token': f'dev-token-{code}',
                'refresh_token': f'dev-refresh-{code}',
                'expires_in': 3600,
            }

        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                },
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            self.access_token = data.get('access_token')
            self._refresh_token = data.get(
                'refresh_token', self._refresh_token
            )
            return data

        except requests.RequestException as e:
            return {'error': str(e)}

    def do_refresh_token(self) -> dict:
        """Refresh the access token using the stored refresh token.

        Note: renamed from `refresh_token` to avoid name collision with
        the `self._refresh_token` attribute.
        """
        if not self._refresh_token:
            return {'error': 'No refresh token available'}

        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': self._refresh_token,
                    'client_id': self.client_id,
                },
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            self.access_token = data.get('access_token')
            self._refresh_token = data.get(
                'refresh_token', self._refresh_token
            )
            return data

        except requests.RequestException as e:
            return {'error': str(e)}

    def get_yandex_account(self) -> str:
        """Get the Yandex account ID using the current access token."""
        if not self.access_token:
            return ''

        try:
            response = requests.get(
                f'{self.YANDEX_HOST}/info',
                headers={'Authorization': f'OAuth {self.access_token}'},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return str(data.get('id', ''))

        except requests.RequestException:
            return ''

    def authorize_with_credentials(self, code: str):
        """Full authorization flow: exchange code and fetch Yandex ID."""
        token_data = self.exchange_code_for_token(code)
        if 'error' in token_data:
            return token_data

        yandex_id = self.get_yandex_account()
        return {
            'access_token': token_data.get('access_token'),
            'refresh_token': token_data.get('refresh_token'),
            'yandex_id': yandex_id,
        }
