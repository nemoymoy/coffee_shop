"""Views for users app."""
from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.utils.decorators import decorator_from_middleware
from django.middleware.csrf import CsrfViewMiddleware

from coffee_shop.apps.users.forms import UserRegistrationForm


@decorator_from_middleware(CsrfViewMiddleware)
def login_view(request):
    """Авторизация пользователя."""
    if request.user.is_authenticated:
        return redirect('catalog:catalog')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
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
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.first_name or user.username}!')
            return redirect('catalog:catalog')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки ниже.')
    else:
        form = UserRegistrationForm()

    return render(request, 'users/register.html', {'form': form})
