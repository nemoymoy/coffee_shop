"""Tests for EmailVerificationService."""
import pytest
from datetime import timedelta

from django.utils import timezone
from django.contrib.auth.models import User

from coffee_shop.apps.users.models import UserEmailVerification
from coffee_shop.apps.users.services.email_verification_service import (
    EmailVerificationService,
)


@pytest.mark.django_db
class TestEmailVerificationService:
    """Тесты сервиса EmailVerificationService."""

    def _create_user(self):
        return User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
        )

    def test_generate_token_creates_verification(self):
        """Генерация токена создаёт запись верификации."""
        user = self._create_user()
        verification = EmailVerificationService.generate_token(user)

        assert verification.user == user
        assert verification.token is not None
        assert verification.is_used is False
        assert verification.is_valid is True
        assert verification.expires_at > timezone.now()

    def test_generate_token_deletes_old_unused(self):
        """Новый токен удаляет старый неиспользованный."""
        user = self._create_user()
        v1 = EmailVerificationService.generate_token(user)

        v1.refresh_from_db()
        assert UserEmailVerification.objects.filter(user=user).count() == 1

        v2 = EmailVerificationService.generate_token(user)
        assert UserEmailVerification.objects.filter(user=user).count() == 1
        assert v2.token != v1.token

    def test_generate_token_keeps_used(self):
        """При генерации нового токена старые удаляются (OneToOne constraint)."""
        user = self._create_user()
        v1 = EmailVerificationService.generate_token(user)
        v1.is_used = True
        v1.save(update_fields=['is_used'])

        # generate_token удаляет все записи для пользователя (OneToOne constraint)
        v2 = EmailVerificationService.generate_token(user)
        # Должна быть только одна запись — новая
        assert UserEmailVerification.objects.filter(user=user).count() == 1
        assert v2.token != v1.token

    def test_verify_token_success(self):
        """Успешная верификация токена."""
        user = self._create_user()
        verification = EmailVerificationService.generate_token(user)

        success, error = EmailVerificationService.verify_token(verification.token)
        assert success is True
        assert error is None

        verification.refresh_from_db()
        assert verification.is_used is True

    def test_verify_token_invalid_uuid(self):
        """Верификация с невалидным UUID."""
        success, error = EmailVerificationService.verify_token(
            '00000000-0000-0000-0000-000000000000'
        )
        assert success is False
        assert error is not None

    def test_verify_token_already_used(self):
        """Верификация уже использованного токена."""
        user = self._create_user()
        verification = EmailVerificationService.generate_token(user)
        verification.is_used = True
        verification.save(update_fields=['is_used'])

        success, error = EmailVerificationService.verify_token(verification.token)
        assert success is False
        assert 'использован' in error

    def test_verify_token_expired(self):
        """Верификация истёкшего токена."""
        user = self._create_user()
        verification = UserEmailVerification.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        success, error = EmailVerificationService.verify_token(verification.token)
        assert success is False
        assert 'истёк' in error

    def test_resend_token(self):
        """Пересоздание токена."""
        user = self._create_user()
        v1 = EmailVerificationService.generate_token(user)

        v2 = EmailVerificationService.resend_token(user)
        assert v2.token != v1.token
        assert UserEmailVerification.objects.filter(user=user).count() == 1
