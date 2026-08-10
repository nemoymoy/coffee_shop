"""Tests for PersonalDataConsent model."""
import pytest
from datetime import datetime
from django.contrib.auth.models import User
from coffee_shop.apps.users.models import PersonalDataConsent


pytestmark = pytest.mark.django_db


class TestPersonalDataConsentModel:
    """Тесты модели согласия на обработку ПД."""

    def test_create_consent(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com',
            first_name='Иван',
            last_name='Петров',
        )
        consent = PersonalDataConsent.objects.create(
            user=user,
            version='1.0',
            content_hash='abc123',
            ip_address='192.168.1.1',
            user_agent='Mozilla/5.0',
        )
        assert consent.user == user
        assert consent.version == '1.0'
        assert consent.content_hash == 'abc123'
        assert consent.ip_address == '192.168.1.1'
        assert consent.user_agent == 'Mozilla/5.0'
        assert consent.consentted_at is not None

    def test_consent_str(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            first_name='Иван',
            last_name='Петров',
        )
        consent = PersonalDataConsent.objects.create(
            user=user,
            version='1.0',
            content_hash='abc123',
        )
        assert 'Иван Петров' in str(consent)
        assert '1.0' in str(consent)

    def test_consent_str_without_name(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        consent = PersonalDataConsent.objects.create(
            user=user,
            version='1.0',
            content_hash='abc123',
        )
        assert 'testuser' in str(consent)

    def test_one_to_one_relationship(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        consent = PersonalDataConsent.objects.create(
            user=user,
            version='1.0',
            content_hash='abc123',
        )
        assert user.personal_data_consent == consent

    def test_consent_defaults(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        consent = PersonalDataConsent.objects.create(
            user=user,
            content_hash='abc123',
        )
        assert consent.version == '1.0'
        assert consent.ip_address is None
        assert consent.user_agent == ''

    def test_consent_ordering(self):
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        consent_old = PersonalDataConsent.objects.create(
            user=user,
            version='1.0',
            content_hash='abc123',
        )
        consent_old.consentted_at = datetime(2025, 1, 1)
        consent_old.save(update_fields=['consented_at'])
        consent_new = PersonalDataConsent.objects.create(
            user=user,
            version='2.0',
            content_hash='def456',
        )
        consents = PersonalDataConsent.objects.filter(user=user)
        assert consents.first() == consent_new
        assert consents.last() == consent_old
