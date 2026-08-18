"""Custom social-auth pipeline steps for Yandex OAuth."""
import hashlib

from django.contrib.auth import get_user_model
from django.utils import timezone

from coffee_shop.apps.users.models import PersonalDataConsent

User = get_user_model()


def auto_link_existing_user(backend, uid, user=None, is_new=False, **kwargs):
    """
    Если пользователь с таким email уже существует, связать Яндекс-аккаунт
    с существующим User, даже если username/uid отличается.
    """
    from social_django.models import UserSocialAuth

    # Получаем email из response Яндекс OAuth
    email = kwargs.get('response', {}).get('email')
    if not email:
        return None

    try:
        existing_user = User.objects.get(email=email)
    except User.DoesNotExist:
        return None

    # Проверяем, уже ли Яндекс-аккаунт привязан к другому пользователю
    other_social = UserSocialAuth.objects.filter(
        uid=uid,
        user__email=email
    ).exclude(user=existing_user)

    if other_social.exists():
        return None

    # Привязываем Яндекс-аккаунт к существующему пользователю
    UserSocialAuth.objects.update_or_create(
        user=existing_user,
        backend=backend.name,
        defaults={
            'uid': uid,
            'extra_data': kwargs.get('response', {}),
        },
    )
    return existing_user


def create_personal_data_consent(backend, uid, user=None, is_new=False, **kwargs):
    """
    Для пользователей, зарегистрированных через Яндекс OAuth,
    автоматически создаём запись PersonalDataConsent.
    """
    if not user or not is_new:
        # Для существующих пользователей consent уже есть
        return None

    if not user.email:
        return None

    # Проверяем, нет ли уже согласия
    if PersonalDataConsent.objects.filter(user=user).exists():
        return None

    # Создаём запись согласия
    consent_version = '1.0'
    consent_text = "Согласие на обработку персональных данных (версия 1.0)"
    content_hash = hashlib.md5(
        consent_text.encode('utf-8')
    ).hexdigest()

    request = kwargs.get('request')
    ip_address = None
    user_agent = ''
    if request:
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:1000]

    # Yandex OAuth не требует явного согласия, так как пользователь
    # уже подтвердил данные через Яндекс
    PersonalDataConsent.objects.create(
        user=user,
        version=consent_version,
        content_hash=content_hash,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return user
