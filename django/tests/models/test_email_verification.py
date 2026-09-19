"""Tests for UserEmailVerification model."""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from coffee_shop.apps.users.models import UserEmailVerification


@pytest.mark.django_db
class TestUserEmailVerificationModel:
    """Тесты модели UserEmailVerification."""

    def test_create_token(self, user):
        """Создание токена верификации."""
        verification = UserEmailVerification.objects.create(
            user=user,
            token=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(hours=24),
        )
        assert verification.user == user
        assert verification.is_used is False
        assert verification.is_valid is True
        assert verification.is_expired is False

    def test_auto_set_expiry(self, user):
        """Автоматическая установка expires_at при save."""
        verification = UserEmailVerification(user=user)
        verification.save()
        assert verification.expires_at is not None
        assert verification.expires_at > timezone.now()

    def test_is_valid_when_unused_and_not_expired(self, user):
        """Токен валиден если не использован и не истёк."""
        verification = UserEmailVerification.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert verification.is_valid is True

    def test_is_expired_when_time_passed(self, user):
        """Токен истёк если время вышло."""
        verification = UserEmailVerification.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        assert verification.is_expired is True
        assert verification.is_valid is False

    def test_is_used_token_becomes_invalid(self, user):
        """Использованный токен невалиден."""
        verification = UserEmailVerification.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        verification.is_used = True
        verification.save(update_fields=['is_used'])
        assert verification.is_used is True
        assert verification.is_valid is False

    def test_one_to_one_relationship(self, user):
        """OneToOne связь с пользователем."""
        verification = UserEmailVerification.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert user.email_verification == verification

    def test_string_representation(self, user):
        """Строковое представление."""
        user.email = 'test@example.com'
        user.save()
        verification = UserEmailVerification.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert 'test@example.com' in str(verification)
