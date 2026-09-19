"""Email verification service."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from coffee_shop.apps.users.models import UserEmailVerification


class EmailVerificationService:
    """Сервис управления токенами подтверждения email."""

    TOKEN_EXPIRY_HOURS = 24

    @classmethod
    def generate_token(cls, user):
        """Генерирует новый токен для пользователя (пересоздаёт старый)."""
        # Удаляем ВСЕ старые токены для пользователя
        UserEmailVerification.objects.filter(user=user).delete()

        return UserEmailVerification.objects.create(
            user=user,
            token=cls._generate_uuid(),
            expires_at=timezone.now() + timedelta(hours=cls.TOKEN_EXPIRY_HOURS),
        )

    @classmethod
    def verify_token(cls, token):
        """Проверяет токен.

        Returns:
            tuple: (success: bool, error: str | None)
        """
        try:
            verification = UserEmailVerification.objects.get(token=token)
        except UserEmailVerification.DoesNotExist:
            return False, 'Недействительный токен'

        if verification.is_used:
            return False, 'Токен уже использован'

        if verification.is_expired:
            return False, 'Токен истёк'

        verification.is_used = True
        verification.save(update_fields=['is_used'])
        return True, None

    @classmethod
    def resend_token(cls, user):
        """Пересоздаёт токен для повторной отправки."""
        return cls.generate_token(user)

    @staticmethod
    def _generate_uuid():
        """Генерирует UUID для токена."""
        import uuid
        return uuid.uuid4()
