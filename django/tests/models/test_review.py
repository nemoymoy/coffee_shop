"""Tests for Review model."""
import pytest
from django.contrib.auth import get_user_model
from coffee_shop.apps.catalog.models import Review, Product


pytestmark = pytest.mark.django_db


class TestReview:
    """Тесты модели Review."""

    @pytest.fixture
    def user(self):
        return get_user_model().objects.create_user(
            username='testuser',
            password='testpass',
            email='test@example.com',
        )

    @pytest.fixture
    def product(self):
        return Product.objects.create(
            name='Test Coffee',
            slug='test-coffee',
            product_type='coffee',
            price_per_50g=500,
            stock=500,
        )

    def test_create_review(self, user, product):
        review = Review.objects.create(
            user=user,
            product=product,
            rating=5,
            comment='Отличный кофе!',
        )
        assert review.rating == 5
        assert review.comment == 'Отличный кофе!'
        assert review.is_approved is False

    def test_review_str(self, user, product):
        user.first_name = 'Иван'
        user.save()
        review = Review.objects.create(
            user=user,
            product=product,
            rating=4,
        )
        expected = f'Иван {user.last_name or ""} → {product.name}'
        assert expected in str(review)

    def test_product_reviews(self, user, product):
        Review.objects.create(user=user, product=product, rating=5)
        Review.objects.create(user=user, product=product, rating=3, comment='Нормально')
        assert product.reviews.count() == 2

    def test_approved_review(self, user, product):
        review = Review.objects.create(
            user=user,
            product=product,
            rating=5,
            is_approved=True,
        )
        assert review.is_approved is True

    def test_rating_range(self, user, product):
        for i in range(1, 6):
            review = Review.objects.create(
                user=user,
                product=product,
                rating=i,
            )
            assert review.rating == i

    def test_reviews_ordering(self, user, product):
        from django.utils import timezone
        r1 = Review.objects.create(user=user, product=product, rating=3)
        import time
        time.sleep(0.01)
        r2 = Review.objects.create(user=user, product=product, rating=5)
        r3 = Review.objects.create(user=user, product=product, rating=4)
        reviews = list(Review.objects.filter(product=product).values_list('pk', flat=True))
        assert reviews[0] == r3.pk
        assert reviews[1] == r2.pk
        assert reviews[2] == r1.pk

    def test_cascade_delete_product(self, user, product):
        review = Review.objects.create(user=user, product=product, rating=5)
        product.delete()
        assert not Review.objects.filter(pk=review.pk).exists()

    def test_cascade_delete_user(self, product):
        user = get_user_model().objects.create_user(username='user2', password='pass', email='u2@t.com')
        review = Review.objects.create(user=user, product=product, rating=4)
        user.delete()
        assert not Review.objects.filter(pk=review.pk).exists()
