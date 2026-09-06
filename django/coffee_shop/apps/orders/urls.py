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
    path('checkout/postamats/', delivery_views.postamats_list_view, name='postamats_list'),
    path('checkout/packages/', delivery_views.packages_list_view, name='packages_list'),
    path('checkout/pvz-locations/', delivery_views.pvz_locations_view, name='pvz_locations'),
    path('checkout/geocode-address/', delivery_views.geocode_address_view, name='geocode_address'),
    path('checkout/yandex-webhook/', delivery_views.yandex_delivery_webhook, name='yandex_webhook'),
    # Order
    path('success/<int:order_id>/', views.order_success, name='order_success'),
    path('detail/<int:pk>/', views.order_detail, name='order_detail'),
    # Payment - YooKassa
    path('pay/<int:order_id>/', views.pay_order, name='pay_order'),
    path('webhook/', views.payment_webhook, name='payment_webhook'),
    path('api/pay/', views.create_payment_api, name='create_payment_api'),
    path('api/payment/status/<str:payment_id>/', views.check_payment_status, name='check_payment_status'),
    path('api/refund/', views.create_refund, name='create_refund'),
    path('payment/result/', views.payment_result, name='payment_result'),
    # Yandex Delivery Status
    path('delivery/status/', delivery_views.yandex_delivery_status_view, name='yandex_delivery_status'),
]
