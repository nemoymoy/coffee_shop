from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'coffee_shop.apps.users'
    verbose_name = 'Пользователи'

    def ready(self):
        # Patch Django User model with social_user property for social-auth
        from django.contrib.auth.models import User
        from social_django.models import UserSocialAuth

        def _get_social_user(self):
            try:
                return UserSocialAuth.objects.get(user=self, provider='yandex')
            except UserSocialAuth.DoesNotExist:
                return None

        def _set_social_user(self, value):
            self._social_user_instance = value

        User.add_to_class('social_user', property(_get_social_user, _set_social_user))
