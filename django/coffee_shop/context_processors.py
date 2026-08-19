"""Template context processors."""
from django.conf import settings


def yandex_metrika(request):
    """Pass Yandex Metrika and Maps settings to templates."""
    return {
        'YANDEX_METRIKA_ID': getattr(settings, 'YANDEX_METRIKA_ID', ''),
        'YANDEX_METRIKA_WEBVIEWER': getattr(settings, 'YANDEX_METRIKA_WEBVIEWER', False),
        'YANDEX_JAVASCRIPT_API_KEY': getattr(settings, 'YANDEX_JAVASCRIPT_API_KEY', ''),
        'YANDEX_GEOCODER_API_KEY': getattr(settings, 'YANDEX_GEOCODER_API_KEY', ''),
        'YANDEX_MAPS_API_KEY': getattr(settings, 'YANDEX_MAPS_API_KEY', ''),
    }
