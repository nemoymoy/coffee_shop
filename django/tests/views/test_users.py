"""Tests for users views."""
import pytest
from django.urls import reverse
from django.contrib.auth.models import User


pytestmark = pytest.mark.django_db


class TestLoginView:
    """Тесты представления авторизации."""

    def test_login_page_loads(self, client):
        response = client.get(reverse('users:login'))
        assert response.status_code == 200
        assert 'Вход в аккаунт'.encode('utf-8') in response.content

    def test_login_successful(self, client):
        User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com',
        )
        response = client.post(
            reverse('users:login'),
            {'username': 'testuser', 'password': 'testpass123'},
            follow=True,
        )
        assert response.status_code == 200

    def test_login_invalid_credentials(self, client):
        response = client.post(
            reverse('users:login'),
            {'username': 'testuser', 'password': 'wrongpass'},
        )
        assert response.status_code == 200
        assert 'Неверное имя пользователя или пароль'.encode('utf-8') in response.content

    def test_authenticated_user_redirected(self, client):
        User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('users:login'))
        assert response.url == reverse('catalog:catalog')


class TestRegisterView:
    """Тесты представления регистрации."""

    def test_register_page_loads(self, client):
        response = client.get(reverse('users:register'))
        assert response.status_code == 200
        assert 'Регистрация'.encode('utf-8') in response.content

    def test_register_successful(self, client):
        response = client.post(
            reverse('users:register'),
            {
                'username': 'newuser',
                'email': 'new@example.com',
                'first_name': 'Иван',
                'last_name': 'Петров',
                'password1': 'strongpass123',
                'password2': 'strongpass123',
                'personal_data_consent': True,
            },
            follow=True,
        )
        assert User.objects.filter(username='newuser').exists()
        assert response.status_code == 200

    def test_register_without_consent_fails(self, client):
        """Регистрация без согласия должна завершиться ошибкой."""
        response = client.post(
            reverse('users:register'),
            {
                'username': 'newuser',
                'email': 'new@example.com',
                'first_name': 'Иван',
                'last_name': 'Петров',
                'password1': 'strongpass123',
                'password2': 'strongpass123',
            },
        )
        assert response.status_code == 200
        assert 'Необходимо дать согласие на обработку персональных данных'.encode('utf-8') in response.content
        assert not User.objects.filter(username='newuser').exists()

    def test_register_creates_consent_record(self, client):
        """Успешная регистрация должна создать запись согласия."""
        response = client.post(
            reverse('users:register'),
            {
                'username': 'newuser',
                'email': 'new@example.com',
                'first_name': 'Иван',
                'last_name': 'Петров',
                'password1': 'strongpass123',
                'password2': 'strongpass123',
                'personal_data_consent': True,
            },
        )
        user = User.objects.get(username='newuser')
        from coffee_shop.apps.users.models import PersonalDataConsent
        assert PersonalDataConsent.objects.filter(user=user).exists()
        consent = PersonalDataConsent.objects.get(user=user)
        assert consent.version == '1.0'
        assert consent.ip_address is not None

    def test_register_duplicate_username(self, client):
        User.objects.create_user(
            username='existing',
            password='testpass123',
            email='existing@example.com',
        )
        response = client.post(
            reverse('users:register'),
            {
                'username': 'existing',
                'email': 'other@example.com',
                'first_name': 'Иван',
                'last_name': 'Петров',
                'password1': 'strongpass123',
                'password2': 'strongpass123',
            },
        )
        assert response.status_code == 200
        assert b'\xd1\x83\xd0\xb6\xd0\xb5 \xd1\x81\xd0\xb8\xd1\x81\xd1\x82\xd0\xb5\xd0\xb5\xd1\x82' in response.content

    def test_register_duplicate_email(self, client):
        User.objects.create_user(
            username='user1',
            password='testpass123',
            email='dup@example.com',
        )
        response = client.post(
            reverse('users:register'),
            {
                'username': 'user2',
                'email': 'dup@example.com',
                'first_name': 'Иван',
                'last_name': 'Петров',
                'password1': 'strongpass123',
                'password2': 'strongpass123',
            },
        )
        assert response.status_code == 200
        assert b'\xd1\x83\xd0\xb6\xd0\xb5 \xd1\x81\xd0\xb8\xd1\x81\xd1\x82\xd0\xb5\xd0\xb5\xd1\x82' in response.content

    def test_register_password_mismatch(self, client):
        response = client.post(
            reverse('users:register'),
            {
                'username': 'newuser',
                'email': 'new@example.com',
                'first_name': 'Иван',
                'last_name': 'Петров',
                'password1': 'pass1234',
                'password2': 'pass5678',
            },
        )
        assert response.status_code == 200
        assert b'\xd1\x83\xd0\xb6\xd0\xb5 \xd1\x81\xd0\xb8\xd1\x81\xd1\x82\xd0\xb5\xd0\xb5\xd1\x82' not in response.content

    def test_authenticated_user_redirected(self, client):
        User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('users:register'))
        assert response.url == reverse('catalog:catalog')


class TestLogoutView:
    """Тесты представления выхода."""

    def test_logout_redirects_to_catalog(self, client):
        User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('users:logout'), follow=True)
        assert response.status_code == 200


class TestDashboardView:
    """Тесты представления личного кабинета."""

    def test_unauthenticated_redirects(self, client):
        response = client.get(reverse('users:dashboard'))
        assert response.status_code == 302
        assert 'users:login' in response.url

    def test_authenticated_sees_dashboard(self, client):
        from decimal import Decimal
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            first_name='Иван',
        )
        client.login(username='testuser', password='testpass123')

        from coffee_shop.apps.orders.models import Order
        Order.objects.create(
            user=user,
            status='new',
            total_amount=Decimal('300.00'),
            delivery_method='pickup',
        )

        response = client.get(reverse('users:dashboard'))
        assert response.status_code == 200
        assert b'orders' in response.content


class TestProfileView:
    """Тесты представления профиля."""

    def test_unauthenticated_redirects(self, client):
        response = client.get(reverse('users:profile'))
        assert response.status_code == 302
        assert 'users:login' in response.url

    def test_profile_page_loads(self, client):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            first_name='Иван',
            email='test@example.com',
        )
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('users:profile'))
        assert response.status_code == 200

    def test_profile_update(self, client):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            first_name='Иван',
            email='test@example.com',
        )
        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:profile'),
            {
                'first_name': 'Петр',
                'last_name': 'Иванов',
                'username': 'testuser',
                'email': 'new@example.com',
            },
        )
        user.refresh_from_db()
        assert user.first_name == 'Петр'
        assert user.email == 'new@example.com'

    def test_profile_password_change_success(self, client):
        user = User.objects.create_user(
            username='testuser',
            password='oldpass123',
            first_name='Иван',
        )
        client.login(username='testuser', password='oldpass123')
        response = client.post(
            reverse('users:profile'),
            {
                'first_name': 'Иван',
                'last_name': '',
                'username': 'testuser',
                'email': 'test@example.com',
                'password_current': 'oldpass123',
                'password_new': 'newpass456',
                'password_confirm': 'newpass456',
            },
        )
        # Verify new password works
        assert client.login(username='testuser', password='newpass456')

    def test_profile_password_change_wrong_current(self, client):
        user = User.objects.create_user(
            username='testuser',
            password='oldpass123',
            first_name='Иван',
        )
        client.login(username='testuser', password='oldpass123')
        response = client.post(
            reverse('users:profile'),
            {
                'first_name': 'Иван',
                'last_name': '',
                'username': 'testuser',
                'email': 'test@example.com',
                'password_current': 'wrongpass',
                'password_new': 'newpass456',
                'password_confirm': 'newpass456',
            },
        )
        # Verify old password still works
        assert client.login(username='testuser', password='oldpass123')


class TestPersonalDataConsentTextView:
    """Тесты представления текста согласия на обработку ПД."""

    def test_consent_text_page_loads(self, client):
        response = client.get(reverse('users:personal_data_consent_text'))
        assert response.status_code == 200
        assert 'персональных данных'.encode('utf-8').lower() in response.content.lower()

    def test_consent_text_contains_pd_list(self, client):
        response = client.get(reverse('users:personal_data_consent_text'))
        assert b'username' in response.content
        assert b'email' in response.content
        assert 'IP-адрес'.encode('utf-8') in response.content

    def test_consent_text_has_link_to_email(self, client):
        response = client.get(reverse('users:personal_data_consent_text'))
        assert b'privacy@coffee-shop.ru' in response.content
