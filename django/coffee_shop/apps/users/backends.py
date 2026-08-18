"""
Custom Yandex OAuth2 backend with name 'yandex'.

The default social_core.backends.yandex.YandexOAuth2 uses name 'yandex-oauth2'
and oauth.yandex.com domain. This wrapper changes both the name to 'yandex'
and the OAuth domain to oauth.yandex.ru (for keys obtained from oauth.yandex.ru).
"""
from social_core.backends.yandex import YandexOAuth2


class YandexOAuth(YandexOAuth2):
    """Yandex OAuth2 backend using oauth.yandex.ru."""

    name = "yandex"
    AUTHORIZATION_URL = "https://oauth.yandex.ru/authorize"
    ACCESS_TOKEN_URL = "https://oauth.yandex.ru/token"
    REDIRECT_STATE = True

    def get_redirect_uri(self, state):
        return "http://localhost:8000/accounts/oauth/complete/yandex/"
