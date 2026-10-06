"""Tests for email verification views and cart restriction."""
import pytest
from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from coffee_shop.apps.users.models import UserEmailVerification
from coffee_shop.apps.users.services.email_verification_service import (
    EmailVerificationService,
)
from social_django.models import UserSocialAuth


@pytest.mark.django_db
class TestRegisterWithVerification:
    """Тесты регистрации с отправкой токена верификации."""

    def test_register_creates_verification_token(self, client):
        """Регистрация создаёт токен верификации."""
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
            'personal_data_consent': True,
        }
        response = client.post(reverse('users:register'), data)
        assert response.status_code == 302  # redirect

        user = User.objects.get(username='newuser')
        assert UserEmailVerification.objects.filter(user=user).exists()

    def test_register_redirects_to_pending(self, client):
        """После регистрации редирект на страницу pending."""
        data = {
            'username': 'newuser2',
            'email': 'new2@example.com',
            'first_name': 'Мария',
            'last_name': 'Сидорова',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
            'personal_data_consent': True,
        }
        response = client.post(reverse('users:register'), data)
        assert response.url == reverse('users:email_verification_pending')

    @patch('coffee_shop.tasks.send_verification_email')
    def test_register_sends_email(self, mock_send, client):
        """Регистрация отправляет email."""
        data = {
            'username': 'newuser3',
            'email': 'new3@example.com',
            'first_name': 'Алексей',
            'last_name': 'Иванов',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
            'personal_data_consent': True,
        }
        client.post(reverse('users:register'), data)
        mock_send.delay.assert_called_once()


@pytest.mark.django_db
class TestVerifyEmailView:
    """Тесты view подтверждения email."""

    def _create_verified_user(self):
        user = User.objects.create_user(
            username='verifyuser',
            email='verify@example.com',
            password='testpass123',
        )
        verification = EmailVerificationService.generate_token(user)
        return user, verification

    def test_verify_email_success(self, client):
        """Успешное подтверждение email с автоматическим входом."""
        user, verification = self._create_verified_user()

        response = client.get(
            reverse('users:verify_email', args=[verification.token])
        )
        assert response.status_code == 302
        # После верификации пользователь должен быть залогинен и редирект на каталог
        assert response.url == reverse('catalog:catalog')
        # Проверка, что пользователь залогинен
        assert response.wsgi_request.user.pk == user.pk

        # Токен удаляется после подтверждения
        assert not UserEmailVerification.objects.filter(
            token=verification.token
        ).exists()

        # Статус верификации в профиле
        user.refresh_from_db()
        assert user.profile.email_verified_at is not None

    def test_verify_email_already_used_redirects_to_login(self, client):
        """Повторный переход по ссылке — токен удалён, ошибка."""
        user, verification = self._create_verified_user()

        # Первый раз подтверждаем
        client.get(
            reverse('users:verify_email', args=[verification.token])
        )

        # Токен удалён, но пользователь уже верифицирован
        assert not UserEmailVerification.objects.filter(
            token=verification.token
        ).exists()
        user.refresh_from_db()
        assert user.profile.email_verified_at is not None

        # Второй раз — токен не найден, пользователь не может войти по удалённому токену
        # Это ожидаемое поведение — токен одноразовый
        response = client.get(
            reverse('users:verify_email', args=[verification.token])
        )
        assert response.status_code == 302
        # Токен не найден — редирект на ошибку
        assert 'verification-error' in response.url

    def test_verify_email_invalid_token(self, client):
        """Подтверждение с невалидным токеном."""
        response = client.get(
            reverse('users:verify_email', args=[
                '00000000-0000-0000-0000-000000000000'
            ])
        )
        assert response.url == reverse('users:email_verification_error')

    def test_verify_email_expired(self, client):
        """Подтверждение истёкшего токена."""
        user, verification = self._create_verified_user()
        verification.expires_at = timezone.now() - timedelta(hours=1)
        verification.save(update_fields=['expires_at'])

        response = client.get(
            reverse('users:verify_email', args=[verification.token])
        )
        assert response.url == reverse('users:email_verification_error')

    def test_verify_email_already_used(self, client):
        """Подтверждение уже использованного токена — токен удалён."""
        user, verification = self._create_verified_user()

        # Первый раз подтверждаем
        client.get(
            reverse('users:verify_email', args=[verification.token])
        )

        # Токен удалён, пользователь верифицирован
        assert not UserEmailVerification.objects.filter(
            token=verification.token
        ).exists()

        # Второй раз — токен не найден, ошибка
        response = client.get(
            reverse('users:verify_email', args=[verification.token])
        )
        assert response.status_code == 302
        # Токен не найден — редирект на ошибку
        assert 'verification-error' in response.url


@pytest.mark.django_db
class TestCartAddEmailVerificationBlocked:
    """Тесты блокировки добавления в корзину для не-верифицированных."""

    def test_cart_add_blocked_without_verification_record(self, client):
        """Добавление в корзину заблокировано если email не подтверждён."""
        user = User.objects.create_user(
            username='novuser',
            email='nov@example.com',
            password='testpass123',
        )
        client.force_login(user)

        response = client.post(
            '/cart/add/',
            {
                'product_id': 1,
                'weight': '100',
                'coffee_form': 'beans',
                'brewing_method': 'turka',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            CONTENT_TYPE='application/x-www-form-urlencoded',
        )
        assert response.status_code == 403
        data = response.json()
        assert data['error'] == 'email_not_verified'


@pytest.mark.django_db
class TestOAuthUserNotBlocked:
    """Тесты, что OAuth-пользователи не блокируются верификацией."""

    def _create_oauth_user(self):
        """Создаёт пользователя с привязанным Яндекс-аккаунтом."""
        user = User.objects.create_user(
            username='oauthuser',
            email='oauth@example.com',
            password='testpass123',
        )
        UserSocialAuth.objects.create(
            user=user,
            provider='yandex',
            uid='yandex:12345',
        )
        return user

    def test_oauth_user_not_blocked_by_middleware(self, client):
        """Middleware не блокирует OAuth-пользователя с email_verified_at."""
        user = self._create_oauth_user()
        # OAuth-пользователь получает email_verified_at через pipeline
        user.profile.email_verified_at = timezone.now()
        user.profile.save()
        client.force_login(user)

        # Dashboard требует авторизации, middleware не должен редиректить
        response = client.get(reverse('users:dashboard'))
        assert response.status_code == 200

    def test_oauth_user_can_add_to_cart(self, client):
        """OAuth-пользователь может добавлять товары в корзину."""
        user = self._create_oauth_user()
        # OAuth-пользователь получает email_verified_at через pipeline
        user.profile.email_verified_at = timezone.now()
        user.profile.save()
        client.force_login(user)

        response = client.post(
            '/cart/add/',
            {
                'product_id': 1,
                'weight': '100',
                'coffee_form': 'beans',
                'brewing_method': 'turka',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            CONTENT_TYPE='application/x-www-form-urlencoded',
        )
        # 400 т.к. product не найден, но НЕ 403 email_not_verified
        assert response.status_code in (400, 404)
        data = response.json()
        assert data['error'] != 'email_not_verified'
