"""Middleware for Coffee Shop."""
import logging
import time
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

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
        if settings.DEBUG is False:
            # HSTS
            response['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )

            # CSP
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' https://cdn.jsdelivr.net; "
                "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
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
