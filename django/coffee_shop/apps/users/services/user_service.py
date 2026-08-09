"""User service for users app."""
from django.contrib.auth import get_user_model
from django.db import transaction

User = get_user_model()


class UserService:
    """Сервис для работы с пользователями."""

    @staticmethod
    @transaction.atomic
    def create_user(
        username: str,
        email: str,
        password: str,
        first_name: str = '',
        last_name: str = '',
    ) -> User:
        """Создание нового пользователя."""
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        return user

    @staticmethod
    def get_user_profile(user: User) -> dict:
        """Получение информации о профиле пользователя."""
        return {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_authenticated': user.is_authenticated,
        }

    @staticmethod
    def update_user_profile(
        user: User,
        first_name: str = None,
        last_name: str = None,
        email: str = None,
    ) -> User:
        """Обновление профиля пользователя."""
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if email is not None:
            user.email = email
        user.save()
        return user
