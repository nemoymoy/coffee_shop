"""Yandex Delivery views — OAuth flow and delivery calculation."""
import uuid

from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseRedirect
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService
from coffee_shop.apps.orders.services.yandex_oauth import YandexOAuth


@login_required
def yandex_delivery_auth(request):
    """Redirect to Yandex OAuth authorization page."""
    oauth = YandexOAuth()
    state = uuid.uuid4().hex
    request.session['yandex_oauth_state'] = state

    auth_url = oauth.get_authorization_url(state=state)
    return HttpResponseRedirect(auth_url)


@login_required
def yandex_delivery_callback(request):
    """Handle Yandex OAuth callback — exchange code for token."""
    code = request.GET.get('code')
    state = request.GET.get('state')

    # Verify state
    saved_state = request.session.pop('yandex_oauth_state', None)
    if state != saved_state:
        messages.error(request, 'Ошибка авторизации: некорректный state')
        return redirect('home')

    if not code:
        messages.error(request, 'Ошибка авторизации: код не получен')
        return redirect('home')

    oauth = YandexOAuth()
    result = oauth.authorize_with_credentials(code)

    if 'error' in result and 'yandex_id' not in result:
        messages.error(request, f'Ошибка авторизации: {result.get("error", "неизвестная ошибка")}')
        return redirect('home')

    # Save tokens in session
    request.session['yandex_delivery_access_token'] = result.get('access_token')
    request.session['yandex_delivery_refresh_token'] = result.get('refresh_token')
    request.session['yandex_delivery_yandex_id'] = result.get('yandex_id', '')

    messages.success(request, 'Яндекс Доставка успешно подключена')
    return redirect('home')


def refresh_yandex_token_if_needed(request):
    """
    Try to use session token, refresh if expired.
    Returns access_token or None.
    """
    access_token = request.session.get('yandex_delivery_access_token')
    refresh_token = request.session.get('yandex_delivery_refresh_token')

    if not access_token:
        return None

    if not access_token.startswith('ya2') and not access_token.startswith('dev-token'):
        # Invalid token format — clear session
        request.session.pop('yandex_delivery_access_token', None)
        request.session.pop('yandex_delivery_refresh_token', None)
        return None

    # Test token by trying to get account
    oauth = YandexOAuth()
    oauth.access_token = access_token

    account_id = oauth.get_yandex_account()
    if not account_id and refresh_token:
        # Token may be expired — try refresh
        refresh_result = oauth.do_refresh_token()
        if 'error' in refresh_result:
            # Refresh failed — clear tokens
            request.session.pop('yandex_delivery_access_token', None)
            request.session.pop('yandex_delivery_refresh_token', None)
            request.session.pop('yandex_delivery_yandex_id', None)
            return None

        access_token = refresh_result.get('access_token')
        request.session['yandex_delivery_access_token'] = access_token
        request.session['yandex_delivery_refresh_token'] = refresh_result.get('refresh_token', refresh_token)

        # Re-resolve account ID
        account_id = oauth.get_yandex_account()

    return access_token


@csrf_exempt
@require_POST
@login_required
def calculate_delivery_view(request):
    """
    Calculate delivery price and ETA.

    POST JSON:
    {
        "city": "moscow",
        "street": "ул. Примерная",
        "house": "1",
        "apartment": "10"
    }

    Returns JSON:
    {
        "success": true,
        "price": 299,
        "eta": "30-45 мин",
        "mock": false
    }
    """
    try:
        import json
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({
            'success': False,
            'error': 'Некорректные данные',
        }, status=400)

    city = data.get('city', 'moscow')
    street = data.get('street', '')
    house = data.get('house', '')
    apartment = data.get('apartment', '')

    address = {
        'city': city,
        'street': street,
        'house': house,
        'apartment': apartment,
    }

    # Get token from session
    access_token = request.session.get('yandex_delivery_access_token')
    if not access_token:
        return JsonResponse({
            'success': True,
            'price': 299,
            'eta': '30-45 мин',
            'mock': True,
        }, status=200)

    service = YandexDeliveryService(access_token=access_token)
    result = service.calculate_price(address)

    if result.get('success'):
        return JsonResponse({
            'success': True,
            'price': result.get('price', 299),
            'eta': result.get('eta', '30-45 мин'),
            'mock': result.get('mock', False),
        })
    else:
        return JsonResponse({
            'success': False,
            'error': result.get('error', 'Ошибка расчёта доставки'),
        }, status=500)
