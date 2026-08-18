from django.urls import path
from .views import delivery_views
from . import order_views as views

app_name = 'orders'

urlpatterns = [
    # Cart
    path('cart/', views.cart_view, name='cart'),
    path('add/', views.cart_add, name='cart_add'),
    path('remove/', views.cart_remove, name='cart_remove'),
    path('promo/check/', views.promo_check, name='promo_check'),
    # Checkout
    path('checkout/', views.checkout_view, name='checkout'),
    path('checkout/calculate-delivery/', delivery_views.calculate_delivery_view, name='calculate_delivery'),
    # Order
    path('success/<int:order_id>/', views.order_success, name='order_success'),
    path('detail/<int:pk>/', views.order_detail, name='order_detail'),
    # Payment
    path('webhook/', views.payment_webhook, name='payment_webhook'),
    # Yandex Delivery OAuth
    path('delivery/auth/', delivery_views.yandex_delivery_auth, name='yandex_delivery_auth'),
    path('delivery/callback/', delivery_views.yandex_delivery_callback, name='yandex_delivery_callback'),
]
