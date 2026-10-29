"""
Custom Yandex OAuth2 backend with name 'yandex'.

The default social_core.backends.yandex.YandexOAuth2 uses name 'yandex-oauth2'
and oauth.yandex.com domain. This wrapper changes both the name to 'yandex'
and the OAuth domain to oauth.yandex.ru (for keys obtained from oauth.yandex.ru).

Redirect URI берется из настроек (SOCIAL_AUTH_YANDEX_REDIRECT_URI),
что позволяет работать как на localhost, так и на production-домене.
"""
from django.core.cache import cache
from social_core.backends.yandex import YandexOAuth2

# Redis key prefix and TTL for OAuth state
_OAUTH_STATE_PREFIX = "oauth_state:"
_OAUTH_STATE_TTL = 600  # 10 minutes


class YandexOAuth(YandexOAuth2):
    """Yandex OAuth2 backend using oauth.yandex.ru.

    Redirect URI берется из настроек (SOCIAL_AUTH_YANDEX_REDIRECT_URI),
    что позволяет работать как на localhost, так и на production-домене.

    Uses server-side Redis storage for OAuth state to work around
    SameSite cookie issues with cross-site OAuth redirects over HTTP.
    """

    name = "yandex"
    AUTHORIZATION_URL = "https://oauth.yandex.ru/authorize"
    ACCESS_TOKEN_URL = "https://oauth.yandex.ru/token"
    REDIRECT_STATE = True
    # Не переопределяем get_redirect_uri — используется значение из настроек

    def get_or_create_state(self):
        """Generate state and store in both session and Redis."""
        if self.STATE_PARAMETER or self.REDIRECT_STATE:
            name = f"{self.name}_state"
            state = self.strategy.session_get(name)
            if state is None:
                state = self.state_token()
                # Store in session (standard flow)
                self.strategy.session_set(name, state)
                # Also store in Redis as fallback for SameSite cookie issues
                cache_key = f"{_OAUTH_STATE_PREFIX}{state}"
                cache.set(cache_key, state, timeout=_OAUTH_STATE_TTL)
        else:
            state = None
        return state

    def get_session_state(self):
        """
        Get OAuth state from server-side cache (Redis), falling back to session.

        This works around SameSite cookie issues: when the browser doesn't send
        the session cookie on cross-site redirects (e.g., from Yandex OAuth),
        we can still validate the state from Redis.
        """
        # Try session first (fast path for same-site requests)
        name = f"{self.name}_state"
        state = self.strategy.session_get(name)
        if state:
            return state

        # Fallback: look up state ID from request in Redis
        request = self.strategy.request
        if request:
            state_id = request.GET.get("state") or request.POST.get("state")
            if state_id:
                cache_key = f"{_OAUTH_STATE_PREFIX}{state_id}"
                stored = cache.get(cache_key)
                if stored:
                    # Clean up the cached state
                    cache.delete(cache_key)
                    return stored

        return None
