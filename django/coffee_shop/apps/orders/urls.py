from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.cart_view, name='cart'),
    path('add/', views.cart_add, name='cart_add'),
    path('remove/', views.cart_remove, name='cart_remove'),
    path('promo/check/', views.promo_check, name='promo_check'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('success/<int:order_id>/', views.order_success, name='order_success'),
    path('detail/<int:pk>/', views.order_detail, name='order_detail'),
    path('webhook/', views.payment_webhook, name='payment_webhook'),
]
