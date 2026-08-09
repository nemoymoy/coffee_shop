"""Tests for users services."""
import pytest
from django.contrib.auth import get_user_model
from coffee_shop.apps.users.services import UserService


User = get_user_model()
pytestmark = pytest.mark.django_db


class TestUserService:
    """Тесты сервиса пользователя."""

    def test_create_user(self):
        user = UserService.create_user(
            username='testuser',
            email='test@example.com',
            password='strongpass123',
            first_name='Иван',
            last_name='Петров',
        )
        assert user.username == 'testuser'
        assert user.email == 'test@example.com'
        assert user.first_name == 'Иван'
        assert user.last_name == 'Петров'
        assert user.check_password('strongpass123')

    def test_get_user_profile(self):
        user = UserService.create_user(
            username='testuser',
            email='test@example.com',
            password='strongpass123',
            first_name='Иван',
            last_name='Петров',
        )
        profile = UserService.get_user_profile(user)
        assert profile['id'] == user.id
        assert profile['username'] == 'testuser'
        assert profile['email'] == 'test@example.com'
        assert profile['first_name'] == 'Иван'
        assert profile['last_name'] == 'Петров'

    def test_update_user_profile(self):
        user = UserService.create_user(
            username='testuser',
            email='test@example.com',
            password='strongpass123',
        )
        updated_user = UserService.update_user_profile(
            user,
            first_name='Петр',
            email='new@example.com',
        )
        assert updated_user.first_name == 'Петр'
        assert updated_user.email == 'new@example.com'
        # last_name should remain empty (not passed)
        assert updated_user.last_name == ''

    def test_update_user_preserves_unmodified_fields(self):
        user = UserService.create_user(
            username='testuser',
            email='test@example.com',
            password='strongpass123',
            first_name='Иван',
        )
        updated_user = UserService.update_user_profile(
            user,
            email='new@example.com',
        )
        # first_name should remain unchanged
        assert updated_user.first_name == 'Иван'
        assert updated_user.email == 'new@example.com'
