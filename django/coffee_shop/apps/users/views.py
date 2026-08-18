"""Views for users app."""
import hashlib

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, authenticate as _authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils.decorators import decorator_from_middleware
from django.middleware.csrf import CsrfViewMiddleware

from coffee_shop.apps.users.forms import UserRegistrationForm
from coffee_shop.apps.users.models import PersonalDataConsent


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
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
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

            return redirect('catalog:catalog')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки ниже.')
    else:
        form = UserRegistrationForm()

    return render(request, 'users/register.html', {'form': form})


@decorator_from_middleware(CsrfViewMiddleware)
def personal_data_consent_text_view(request):
    """Отображение текста согласия на обработку персональных данных."""
    return render(request, 'users/personal_data_consent_text.html')
