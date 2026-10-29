"""Custom social-auth pipeline steps for Yandex OAuth."""
import hashlib

from django.contrib.auth import get_user_model
from django.utils import timezone

from coffee_shop.apps.users.models import PersonalDataConsent, UserProfile

User = get_user_model()


def auto_link_existing_user(backend, uid, user=None, is_new=False, **kwargs):
    """
    If a user with this email already exists, link the Yandex account
    to the existing User.

    Must return a dict — run_pipeline stops on non-dict returns.
    """
    from social_django.models import UserSocialAuth

    email = kwargs.get('response', {}).get('email')
    if not email:
        return {'user': user}

    try:
        existing_user = User.objects.get(email=email)
    except User.DoesNotExist:
        return {'user': user}

    other_social = UserSocialAuth.objects.filter(
        uid=uid,
        user__email=email
    ).exclude(user=existing_user)

    if other_social.exists():
        return {'user': user}

    UserSocialAuth.objects.update_or_create(
        user=existing_user,
        backend=backend.name,
        defaults={
            'uid': uid,
            'extra_data': kwargs.get('response', {}),
        },
    )
    return {'user': existing_user}


def create_personal_data_consent(backend, uid, user=None, is_new=False, **kwargs):
    """
    For users registered via Yandex OAuth, automatically create
    a PersonalDataConsent record.

    Must return a dict — run_pipeline stops on non-dict returns.
    """
    if not user or not is_new:
        return {}

    if not user.email:
        return {}

    if PersonalDataConsent.objects.filter(user=user).exists():
        return {}

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

    PersonalDataConsent.objects.create(
        user=user,
        version=consent_version,
        content_hash=content_hash,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {}


def filter_oauth_response_fields(backend, uid, user=None, is_new=False, **kwargs):
    """
    Remove fields from the OAuth response that are not User model attributes.

    Must return a dict — run_pipeline stops on non-dict returns.
    """
    if not user:
        return {}

    response = kwargs.get('response')
    if response and isinstance(response, dict):
        unsafe_fields = {'is_new', 'is_challenge_user', 'is_fake',
                         'is_expert', 'is_know_about_developers',
                         'is_community', 'is_operator_channel'}
        for field in unsafe_fields:
            response.pop(field, None)

    extra_data = kwargs.get('extra_data')
    if extra_data and isinstance(extra_data, dict):
        unsafe_fields = {'is_new', 'is_challenge_user', 'is_fake',
                         'is_expert', 'is_know_about_developers',
                         'is_community', 'is_operator_channel'}
        for field in unsafe_fields:
            extra_data.pop(field, None)

    return {}


def ensure_is_new_attribute(backend, uid, user=None, is_new=False, **kwargs):
    """
    Ensure the User object has an 'is_new' attribute.

    social_core.actions._login_user accesses authenticated_user.is_new.
    The default create_user pipeline step sets is_new as a kwarg, not as
    an attribute on the user object. For existing users (OAuth login),
    is_new is never set at all. This causes AttributeError.

    Must return a dict — run_pipeline stops on non-dict returns.
    """
    if user is not None:
        user.is_new = is_new
    return {'is_new': is_new}


def set_oauth_email_verified(backend, uid, user=None, is_new=False, **kwargs):
    """
    For users who authenticated via OAuth (Yandex), automatically
    mark the email as verified.

    Must return a dict — run_pipeline stops on non-dict returns.
    """
    if not user:
        return {}

    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)

    if profile.email_verified_at is None:
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=['email_verified_at'])

    return {}
