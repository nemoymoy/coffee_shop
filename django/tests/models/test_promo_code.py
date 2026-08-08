"""Tests for PromoCode model."""
import pytest
from django.utils import timezone
from coffee_shop.apps.orders.models import PromoCode


pytestmark = pytest.mark.django_db


class TestPromoCode:
    """Тесты модели PromoCode."""

    @pytest.fixture
    def future_date(self):
        return timezone.now() + timezone.timedelta(days=1)

    @pytest.fixture
    def past_date(self):
        return timezone.now() - timezone.timedelta(days=1)

    def test_create_promo_code(self):
        code = PromoCode.objects.create(
            code='SAVE10',
            discount_type='percent',
            discount_value=10,
            valid_from=timezone.now(),
            valid_to=timezone.now() + timezone.timedelta(days=30),
        )
        assert code.code == 'SAVE10'
        assert code.max_uses == 0
        assert code.used_count == 0

    def test_is_valid_active(self):
        now = timezone.now()
        code = PromoCode.objects.create(
            code='ACTIVE',
            discount_type='percent',
            discount_value=15,
            valid_from=now - timezone.timedelta(days=1),
            valid_to=now + timezone.timedelta(days=1),
            is_active=True,
        )
        assert code.is_valid is True

    def test_is_valid_expired(self, past_date):
        code = PromoCode.objects.create(
            code='EXPIRED',
            discount_type='percent',
            discount_value=10,
            valid_from=past_date - timezone.timedelta(days=10),
            valid_to=past_date,
        )
        assert code.is_valid is False

    def test_is_valid_not_started(self, future_date):
        code = PromoCode.objects.create(
            code='FUTURE',
            discount_type='percent',
            discount_value=10,
            valid_from=future_date,
            valid_to=future_date + timezone.timedelta(days=10),
        )
        assert code.is_valid is False

    def test_is_valid_not_active(self):
        code = PromoCode.objects.create(
            code='INACTIVE',
            discount_type='percent',
            discount_value=10,
            valid_from=timezone.now() - timezone.timedelta(days=1),
            valid_to=timezone.now() + timezone.timedelta(days=1),
            is_active=False,
        )
        assert code.is_valid is False

    def test_remaining_uses_no_limit(self):
        code = PromoCode.objects.create(
            code='UNLIMITED',
            discount_type='fixed',
            discount_value=500,
            max_uses=0,
            used_count=10,
            valid_from=timezone.now(),
            valid_to=timezone.now() + timezone.timedelta(days=30),
        )
        assert code.remaining_uses == 0

    def test_remaining_uses_with_limit(self):
        code = PromoCode.objects.create(
            code='LIMITED',
            discount_type='percent',
            discount_value=10,
            max_uses=5,
            used_count=3,
            valid_from=timezone.now(),
            valid_to=timezone.now() + timezone.timedelta(days=30),
        )
        assert code.remaining_uses == 2

    def test_remaining_uses_exhausted(self):
        code = PromoCode.objects.create(
            code='EXHAUSTED',
            discount_type='percent',
            discount_value=10,
            max_uses=3,
            used_count=3,
            valid_from=timezone.now(),
            valid_to=timezone.now() + timezone.timedelta(days=30),
        )
        assert code.remaining_uses == 0
        assert code.is_valid is False

    def test_str(self):
        code = PromoCode.objects.create(
            code='SAVE100',
            discount_type='percent',
            discount_value=20,
            valid_from=timezone.now(),
            valid_to=timezone.now() + timezone.timedelta(days=30),
        )
        assert str(code) == 'SAVE100'

    def test_unique_code(self):
        PromoCode.objects.create(
            code='SINGLE',
            discount_type='percent',
            discount_value=5,
            valid_from=timezone.now(),
            valid_to=timezone.now() + timezone.timedelta(days=30),
        )
        with pytest.raises(Exception):
            PromoCode.objects.create(
                code='SINGLE',
                discount_type='fixed',
                discount_value=100,
                valid_from=timezone.now(),
                valid_to=timezone.now() + timezone.timedelta(days=30),
            )
