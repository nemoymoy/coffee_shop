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

    @patch('coffee_shop.apps.users.views.send_verification_email')
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
        """Успешное подтверждение email."""
        user, verification = self._create_verified_user()

        response = client.get(
            reverse('users:verify_email', args=[verification.token])
        )
        assert response.status_code == 302  # redirect to success
        assert response.url == reverse('users:email_verified')

        verification.refresh_from_db()
        assert verification.is_used is True

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
        """Подтверждение уже использованного токена."""
        user, verification = self._create_verified_user()
        verification.is_used = True
        verification.save(update_fields=['is_used'])

        response = client.get(
            reverse('users:verify_email', args=[verification.token])
        )
        assert response.url == reverse('users:email_verification_error')


@pytest.mark.django_db
class TestCartAddEmailVerificationBlocked:
    """Тесты блокировки добавления в корзину для не-верифицированных."""

    def _create_user_with_verification(self):
        user = User.objects.create_user(
            username='cartuser',
            email='cart@example.com',
            password='testpass123',
        )
        verification = EmailVerificationService.generate_token(user)
        return user, verification

    def test_cart_add_blocked_for_unverified(self, client):
        """Добавление в корзину заблокировано для не-верифицированных."""
        user, verification = self._create_verified_user()
        client.force_login(user)

        response = client.post(
            reverse('orders:cart_add'),
            {
                'product_id': 1,
                'weight': '100',
                'coffee_form': 'beans',
                'brewing_method': 'turka',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert response.status_code == 403
        data = response.json()
        assert data['error'] == 'email_not_verified'

    def test_cart_add_allowed_for_verified(self, client, coffee_beans):
        """Добавление в корзину разрешено для верифицированных."""
        user, verification = self._create_verified_user()
        verification.is_used = True
        verification.save(update_fields=['is_used'])
        client.force_login(user)

        response = client.post(
            reverse('orders:cart_add'),
            {
                'product_id': coffee_beans.pk,
                'weight': '100',
                'coffee_form': 'beans',
                'brewing_method': 'turka',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_cart_add_blocked_without_verification_record(self, client):
        """Добавление в корзину заблокировано если нет записи верификации."""
        user = User.objects.create_user(
            username='novuser',
            email='nov@example.com',
            password='testpass123',
        )
        client.force_login(user)

        response = client.post(
            reverse('orders:cart_add'),
            {
                'product_id': 1,
                'weight': '100',
                'coffee_form': 'beans',
                'brewing_method': 'turka',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert response.status_code == 403
        data = response.json()
        assert data['error'] == 'email_not_verified'
