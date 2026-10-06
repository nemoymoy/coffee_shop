"""Views for users app."""
import hashlib
import json
import logging

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, authenticate as _authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils.decorators import decorator_from_middleware
from django.middleware.csrf import CsrfViewMiddleware
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods

from coffee_shop.apps.users.forms import UserRegistrationForm, DeliveryAddressForm
from coffee_shop.apps.users.models import (
    PersonalDataConsent, UserEmailVerification, DeliveryAddress,
)
from coffee_shop.apps.users.services.email_verification_service import EmailVerificationService
from coffee_shop.apps.orders.services.geocoder_service import YandexGeocoderService

logger = logging.getLogger(__name__)

# Тексты согласия для версионирования
CONSENT_TEXTS = {
    '1.0': "Согласие на обработку персональных данных (версия 1.0 от 10.08.2026)",
}


@decorator_from_middleware(CsrfViewMiddleware)
def login_view(request):
    """Авторизация пользователя."""
    if request.user.is_authenticated:
        return redirect('catalog:catalog')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Добро пожаловать, {user.first_name or user.username}!')
            next_url = request.GET.get('next', 'catalog:catalog')
            return redirect(next_url)
        else:
            messages.error(request, 'Неверное имя пользователя или пароль.')
    else:
        form = AuthenticationForm()

    return render(request, 'users/login.html', {'form': form})


def register_view(request):
    """Регистрация нового пользователя."""
    if request.user.is_authenticated:
        return redirect('catalog:catalog')

    if request.method == 'POST':
        form = UserRegistrationForm(data=request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Добро пожаловать, {user.first_name or user.username}!')

            # Создаем запись согласия на обработку ПД
            consent_version = '1.0'
            consent_text = CONSENT_TEXTS.get(consent_version, '')
            content_hash = hashlib.md5(
                consent_text.encode('utf-8')
            ).hexdigest()

            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:1000]

            PersonalDataConsent.objects.create(
                user=user,
                version=consent_version,
                content_hash=content_hash,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # Генерируем токен верификации email
            verification = EmailVerificationService.generate_token(user)

            # Отправляем письмо асинхронно через Celery
            # Если Celery недоступен — отправляем синхронно
            try:
                from coffee_shop.tasks import send_verification_email
                result = send_verification_email.delay(user.pk, verification.token)
                # Проверяем, выполнена ли задача сразу (fallback)
                if result.status == 'SUCCESS':
                    pass  # задача выполнена асинхронно
                else:
                    # Celery недоступен — пробуем синхронно
                    send_verification_email(user.pk, verification.token)
            except Exception:
                # Celery недоступен — отправляем синхронно
                from coffee_shop.tasks import send_verification_email
                send_verification_email(user.pk, verification.token)

            messages.info(
                request,
                'На ваш email отправлено письмо с подтверждением. '
                'Пожалуйста, подтвердите email для доступа ко всем функциям сайта.'
            )
            return redirect('users:email_verification_pending')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки ниже.')
    else:
        form = UserRegistrationForm()

    return render(request, 'users/register.html', {'form': form})


@decorator_from_middleware(CsrfViewMiddleware)
def personal_data_consent_text_view(request):
    """Отображение текста согласия на обработку персональных данных."""
    return render(request, 'users/personal_data_consent_text.html')


def verify_email_view(request, token):
    """Подтверждение email по токену с автоматическим входом."""
    # Пытаемся найти токен (может быть ещё не использован)
    user = None
    try:
        verification = UserEmailVerification.objects.get(token=token)
        user = verification.user
    except UserEmailVerification.DoesNotExist:
        # Токен не найден — возможно уже использован и удалён
        pass

    success, error = EmailVerificationService.verify_token(token)

    if success:
        # Автоматический вход после подтверждения email
        if user:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(
                request,
                f'Email подтверждён! Добро пожаловать, {user.first_name or user.username}!'
            )
            return redirect('catalog:catalog')
        
        messages.success(request, 'Email успешно подтверждён!')
        return redirect('users:email_verified')
    else:
        # Токен не найден — проверяем, верифицирован ли пользователь
        if 'Недействительный токен' in error:
            # Токен уже удалён — проверяем профиль пользователя
            if user and user.profile.is_email_verified:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                messages.success(
                    request,
                    f'Email уже подтверждён. Добро пожаловать, {user.first_name or user.username}!'
                )
                return redirect('catalog:catalog')
            
            # Если user=None, токен полностью невалиден
            messages.error(request, error)
            return redirect('users:email_verification_error')
        
        # Если токен уже использован — пробуем залогинить пользователя
        if 'использован' in error and user:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(
                request,
                f'Email уже подтверждён. Добро пожаловать, {user.first_name or user.username}!'
            )
            return redirect('catalog:catalog')
        
        messages.error(request, error)
        return redirect('users:email_verification_error')


@decorator_from_middleware(CsrfViewMiddleware)
def resend_verification_view(request):
    """Повторная отправка токена подтверждения (для авторизованных)."""
    if not request.user.is_authenticated:
        return redirect('users:login')

    if request.method == 'POST':
        verification = EmailVerificationService.resend_token(request.user)
        from coffee_shop.tasks import send_verification_email
        send_verification_email.delay(request.user.pk, verification.token)
        messages.success(
            request,
            'Новое письмо с подтверждением отправлено. Проверьте почту.'
        )

    return redirect('users:email_verification_pending')


# ==================== Delivery Address API Views ====================

@login_required
@require_http_methods(['GET', 'POST'])
def delivery_addresses_view(request):
    """
    API для управления адресами доставки.

    GET — список адресов пользователя
    POST — создание нового адреса
    """
    if request.method == 'GET':
        return _list_addresses(request)
    return _create_address(request)


@login_required
@require_http_methods(['GET', 'PUT', 'PATCH'])
def delivery_address_detail_view(request, address_id):
    """
    API для детального управления адресом доставки.

    GET — получение адреса
    PUT/PATCH — обновление адреса
    """
    try:
        address = DeliveryAddress.objects.get(
            id=address_id,
            user=request.user
        )
    except DeliveryAddress.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Адрес не найден',
        }, status=404)

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'address': _address_to_dict(address),
        })

    return _update_address(request, address)


@login_required
@require_POST
def delivery_address_delete_view(request, address_id):
    """Удаление адреса доставки."""
    try:
        address = DeliveryAddress.objects.get(
            id=address_id,
            user=request.user
        )
    except DeliveryAddress.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Адрес не найден',
        }, status=404)

    address.delete()
    return JsonResponse({
        'success': True,
        'message': 'Адрес удалён',
    })


def _list_addresses(request):
    """Возвращает список адресов пользователя."""
    addresses = DeliveryAddress.objects.filter(user=request.user)
    return JsonResponse({
        'success': True,
        'addresses': [_address_to_dict(addr) for addr in addresses],
    })


def _create_address(request):
    """Создаёт новый адрес пользователя."""
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    label = data.get('label', '')
    full_address = data.get('full_address', '')
    coordinates = data.get('coordinates', '')
    apartment = data.get('apartment', '')
    is_default = data.get('is_default', False)

    if not label or not full_address:
        return JsonResponse({
            'success': False,
            'error': 'Укажите метку и адрес',
        }, status=400)

    # Если координаты не переданы, попробуем геокодировать адрес
    if not coordinates and full_address:
        geocoder = YandexGeocoderService()
        geo_result = geocoder.geocode_first(full_address)
        if geo_result.get('success'):
            coords = geo_result.get('coords', [])
            if coords and len(coords) >= 2:
                coordinates = f'{coords[0]},{coords[1]}'
                full_address = geo_result.get('text', full_address)

    form = DeliveryAddressForm(data={
        'label': label,
        'full_address': full_address,
        'apartment': apartment,
    })

    if not form.is_valid():
        return JsonResponse({
            'success': False,
            'error': 'Ошибка в данных адреса',
            'errors': form.errors,
        }, status=400)

    address = form.save(commit=False)
    address.user = request.user
    address.coordinates = coordinates
    address.is_default = is_default
    address.save()

    return JsonResponse({
        'success': True,
        'address': _address_to_dict(address),
    }, status=201)


def _update_address(request, address):
    """Обновляет адрес пользователя."""
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
    except (json.JSONDecodeError, ValueError):
        data = request.POST

    label = data.get('label', address.label)
    apartment = data.get('apartment', address.apartment)
    is_default = data.get('is_default', address.is_default)

    form = DeliveryAddressForm(
        instance=address,
        data={'label': label, 'full_address': address.full_address, 'apartment': apartment},
    )

    if not form.is_valid():
        return JsonResponse({
            'success': False,
            'error': 'Ошибка в данных адреса',
            'errors': form.errors,
        }, status=400)

    # Сохраняем данные из формы
    form.save()

    # Обновляем is_default (не через form, т.к. это не в fields)
    if is_default != address.is_default:
        address.is_default = is_default
        address.save()

    return JsonResponse({
        'success': True,
        'address': _address_to_dict(address),
    })


def _address_to_dict(address):
    """Конвертирует модель адреса в словарь для JSON."""
    return {
        'id': address.pk,
        'label': address.label,
        'full_address': address.full_address,
        'apartment': address.apartment,
        'coordinates': address.coordinates,
        'is_default': address.is_default,
        'display_address': address.display_address,
        'created_at': address.created_at.isoformat(),
    }
