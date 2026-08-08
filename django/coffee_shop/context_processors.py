"""Template context processors."""
from django.conf import settings


def yandex_metrika(request):
    """Pass Yandex Metrika settings to templates."""
    return {
        'YANDEX_METRIKA_ID': getattr(settings, 'YANDEX_METRIKA_ID', ''),
        'YANDEX_METRIKA_WEBVIEWER': getattr(settings, 'YANDEX_METRIKA_WEBVIEWER', False),
    }
