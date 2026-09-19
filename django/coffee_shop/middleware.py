"""Middleware for Coffee Shop."""
import logging
import time

from django.conf import settings
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from coffee_shop.apps.users.models import UserEmailVerification

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """Log all HTTP requests and responses."""

    def process_request(self, request):
        start_time = time.time()
        request._request_start_time = start_time

        logger.info(
            'REQUEST START: %s %s | IP: %s | User: %s',
            request.method,
            request.get_full_path(),
            self._get_client_ip(request),
            request.user.pk if request.user.is_authenticated else 'anonymous',
        )

    def process_response(self, request, response):
        duration = 0
        if hasattr(request, '_request_start_time'):
            duration = time.time() - request._request_start_time

        logger.info(
            'RESPONSE: %s %s -> %d | %0.3fs',
            request.method,
            request.get_full_path(),
            response.status_code,
            duration,
        )
        return response

    @staticmethod
    def _get_client_ip(request):
        """Get real client IP through proxy."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Add security headers to responses."""

    def process_response(self, request, response):
        # HSTS — только для production
        if settings.DEBUG is False:
            response['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )

        # CSP — всегда, чтобы работали сервисы Яндекса и ЮКасса
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.jsdelivr.net "
            "https://api-maps.yandex.ru https://api-maps.yandex.com "
            "https://yastatic.net "
            "https://core-renderer-tiles.maps.yandex.net "
            "https://tiles.maps.yandex.net "
            "https://static.delivery.yandex.ru "
            "https://cdn1.delivery.yandex.net "
            "https://cdn2.delivery.yandex.net "
            "https://cdn.delivery.yandex.ru "
            "https://taxi.yandex.ru "
            "https://yandex.ru "
            "https://avatars.mds.yandex.net "
            "https://smart-yandex.yandex.net "
            "https://static.yoomoney.ru https://core.yoomoney.ru "
            "https://*.yoomoney.ru; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline' https://yastatic.net; "
            "img-src 'self' data: https: https://avatars.mds.yandex.net https://smart-yandex.yandex.net https://core-renderer-tiles.maps.yandex.net https://tiles.maps.yandex.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self' "
            "https://mc.yandex.ru https://mc.yandex.md https://mc.yandex.kz https://mc.yandex.com "
            "https://mc.admetrica.ru https://mc.admetrica.com "
            "https://mc.webvisor.com https://mc.webvisor.org "
            "https://yandex.ru https://autofill.yandex.ru https://passport.yandex.ru "
            "https://api.yandex.ru https://api.passport.yandex.ru "
            "https://b2b-authproxy.taxi.yandex.net "
            "https://trust.yandex.ru https://trust.yandex.com "
            "https://suggest-maps.yandex.net "
            "https://log.api-maps.yandex.ru "
            "https://maps-static.yandex.net "
            "https://maps-api.yandex.com "
            "https://api-maps.yandex.ru/services/coverage/v2/ "
            "https://core-renderer-tiles.maps.yandex.net/tiles "
            "https://*.disk.yandex.net "
            "https://*.captcha.yandex.net "
            "https://kards.fp.yandex.net "
            "wss://mc.yandex.ru wss://mc.yandex.md wss://mc.yandex.kz wss://mc.yandex.com "
            "wss://delivery.yandex.ru; "
            "frame-src 'self' https://dostavka.yandex.ru https://delivery.yandex.ru https://yandex.ru https://mc.yandex.ru https://yandex.ru/maps https://yoomoney.ru https://*.yoomoney.ru; "
            "frame-ancestors 'self' https://dostavka.yandex.ru https://delivery.yandex.ru;"
        )

        # Hardened headers (also apply in dev for consistency)
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        return response


class RateLimitingMiddleware(MiddlewareMixin):
    """Rate limiting backed by Redis for multi-worker support."""

    LIMITS = {
        '/cart/add/': (30, 60),
        '/checkout/': (10, 60),
        '/pay/': (5, 60),
    }

    def _get_redis_client(self):
        """Lazy import and connect to Redis."""
        from redis import Redis
        return Redis(
            host=settings.REDIS_URL.split('://')[1].split(':')[0]
            if '://' in settings.REDIS_URL
            else 'localhost',
            port=6379,
            decode_responses=False,
        )

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Skip rate limiting for test environment and superusers
        if getattr(settings, 'TESTING', False):
            return None
        if request.user.is_staff and request.user.is_authenticated:
            return None

        path = request.path

        for pattern, (max_requests, window_seconds) in self.LIMITS.items():
            if pattern in path:
                break
        else:
            return None

        ip = self._get_client_ip(request)
        now = time.time()
        window_start = now - window_seconds

        try:
            client = self._get_redis_client()
            redis_key = f'ratelimit:{ip}:{path}'

            # Use Redis pipeline for atomicity
            pipe = client.pipeline()
            pipe.lrange(redis_key, 0, -1)
            results = pipe.execute()[0]

            # Filter old entries
            valid_times = [
                int(t) for t in results
                if int(t) > window_start
            ]

            if len(valid_times) >= max_requests:
                logger.warning(
                    'RATE LIMIT exceeded: %s %s | IP: %s',
                    request.method, path, ip,
                )
                from django.http import JsonResponse
                return JsonResponse(
                    {'error': 'Слишком много запросов. Попробуйте позже.'},
                    status=429,
                )

            # Add current request and keep only the window
            valid_times.append(int(now))
            valid_times = valid_times[-max_requests:]

            pipe = client.pipeline()
            pipe.delete(redis_key)
            for t in valid_times:
                pipe.lpush(redis_key, t)
            pipe.expire(redis_key, window_seconds + 1)
            pipe.execute()

        except Exception as e:
            logger.error('Redis rate limit error: %s', e)
            # Fail open — allow the request if Redis is down

        return None


class EmailVerificationMiddleware(MiddlewareMixin):
    """
    Перенаправляет пользователей с неподтверждённым email
    на страницу pending. Исключения: login, register, verify, health, static.
    """

    EXEMPT_PATTERNS = [
        '/accounts/login/',
        '/accounts/register/',
        '/accounts/verify-email/',
        '/accounts/verification-pending/',
        '/accounts/verification-success/',
        '/accounts/verification-error/',
        '/accounts/resend-verification/',
        '/health/',
        '/accounts/oauth/',
        '/static/',
        '/media/',
    ]

    def __call__(self, request):
        # Skip for test environment
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)

        if (
            request.user.is_authenticated
            and not self._is_email_verified(request.user)
        ):
            path = request.path
            if not self._is_exempt(path):
                # Only use messages if MessageMiddleware is installed
                if hasattr(request, 'session'):
                    from django.contrib import messages
                    messages.info(
                        request,
                        'Для доступа к функционалу сайта подтвердите ваш email.'
                    )
                return redirect('users:email_verification_pending')

        return self.get_response(request)

    @staticmethod
    def _is_email_verified(user):
        """Проверяет, что email подтверждён.

        OAuth-пользователи считаются верифицированными автоматически,
        т.к. email уже подтверждён провайдером (Яндекс).
        """
        try:
            return user.email_verification.is_valid
        except UserEmailVerification.DoesNotExist:
            # OAuth-пользователи — email уже подтверждён Яндексом
            from social_django.models import UserSocialAuth
            has_social_auth = UserSocialAuth.objects.filter(
                user=user
            ).exists()
            if has_social_auth:
                return True
            return False

    @staticmethod
    def _is_exempt(path):
        return any(path.startswith(p) for p in EmailVerificationMiddleware.EXEMPT_PATTERNS)
