"""URLs for users app."""
from django.urls import path
from django.contrib.auth import views as auth_views
from coffee_shop.views import dashboard_view, profile_view
from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(
        next_page='catalog:catalog'), name='logout'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('profile/', profile_view, name='profile'),
]
