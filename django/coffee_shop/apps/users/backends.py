"""
Custom Yandex OAuth2 backend with name 'yandex'.

The default social_core.backends.yandex.YandexOAuth2 uses name 'yandex-oauth2'
and oauth.yandex.com domain. This wrapper changes both the name to 'yandex'
and the OAuth domain to oauth.yandex.ru (for keys obtained from oauth.yandex.ru).

Redirect URI берётся из настроек (SOCIAL_AUTH_YANDEX_REDIRECT_URI),
что позволяет работать как на localhost, так и на production-домене.
"""
from social_core.backends.yandex import YandexOAuth2


class YandexOAuth(YandexOAuth2):
    """Yandex OAuth2 backend using oauth.yandex.ru.

    Redirect URI берётся из настроек (SOCIAL_AUTH_YANDEX_REDIRECT_URI),
    что позволяет работать как на localhost, так и на production-домене.
    """

    name = "yandex"
    AUTHORIZATION_URL = "https://oauth.yandex.ru/authorize"
    ACCESS_TOKEN_URL = "https://oauth.yandex.ru/token"
    REDIRECT_STATE = True
    # Не переопределяем get_redirect_uri — используется значение из настроек
