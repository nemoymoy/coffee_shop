"""Tests for users forms."""
import pytest
from django.contrib.auth.models import User
from coffee_shop.apps.users.forms import UserUpdateForm, UserRegistrationForm


pytestmark = pytest.mark.django_db


class TestUserUpdateForm:
    """Тесты формы обновления профиля."""

    def test_form_valid_data(self):
        form = UserUpdateForm(data={
            'first_name': 'Иван',
            'last_name': 'Петров',
            'username': 'testuser',
            'email': 'test@example.com',
        })
        assert form.is_valid()

    def test_form_empty_username_fails(self):
        form = UserUpdateForm(data={
            'first_name': 'Иван',
            'last_name': 'Петров',
            'username': '',
            'email': 'test@example.com',
        })
        assert not form.is_valid()
        assert 'username' in form.errors

    def test_form_invalid_email_fails(self):
        form = UserUpdateForm(data={
            'first_name': 'Иван',
            'last_name': 'Петров',
            'username': 'testuser',
            'email': 'invalid-email',
        })
        assert not form.is_valid()
        assert 'email' in form.errors


class TestUserRegistrationForm:
    """Тесты формы регистрации."""

    def test_form_valid_data(self):
        form = UserRegistrationForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
            'personal_data_consent': True,
        })
        assert form.is_valid()

    def test_form_password_mismatch(self):
        form = UserRegistrationForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'pass1234',
            'password2': 'pass5678',
        })
        assert not form.is_valid()
        assert 'password2' in form.errors

    def test_form_duplicate_username(self):
        User.objects.create_user(username='existing', password='testpass123')
        form = UserRegistrationForm(data={
            'username': 'existing',
            'email': 'other@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
        })
        assert not form.is_valid()
        assert 'username' in form.errors

    def test_form_duplicate_email(self):
        User.objects.create_user(username='user1', password='testpass123', email='dup@example.com')
        form = UserRegistrationForm(data={
            'username': 'user2',
            'email': 'dup@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
        })
        assert not form.is_valid()
        assert 'email' in form.errors

    def test_form_weak_password(self):
        form = UserRegistrationForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': '123',
            'password2': '123',
        })
        assert not form.is_valid()

    def test_form_save_creates_user(self):
        form = UserRegistrationForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
            'personal_data_consent': True,
        })
        form.is_valid()
        user = form.save()
        assert user.username == 'newuser'
        assert user.email == 'new@example.com'
        assert user.first_name == 'Иван'
        assert user.last_name == 'Петров'
        assert user.check_password('strongpass123')

    def test_form_requires_consent(self):
        """Регистрация без согласия на обработку ПД должна быть невалидна."""
        form = UserRegistrationForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
        })
        assert not form.is_valid()
        assert 'personal_data_consent' in form.errors
        consent_error = ' '.join(form.errors['personal_data_consent'])
        assert 'Необходимо дать согласие на обработку персональных данных' in consent_error

    def test_form_valid_with_consent(self):
        """Регистрация с согласием должна быть валидна."""
        form = UserRegistrationForm(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'first_name': 'Иван',
            'last_name': 'Петров',
            'password1': 'strongpass123',
            'password2': 'strongpass123',
            'personal_data_consent': True,
        })
        assert form.is_valid()
        assert 'personal_data_consent' not in form.errors
