"""DRF serializers for orders app."""
from rest_framework import serializers
from .models import Order, OrderItem, PromoCode


class OrderItemMinimalSerializer(serializers.ModelSerializer):
    """Минимальный сериализатор позиции заказа."""

    product_name = serializers.CharField(
        source='product.name',
        read_only=True,
        label='Название товара'
    )

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product_name',
            'quantity',
            'unit_price',
            'total_price',
            'coffee_weight_grams',
            'coffee_form',
            'brewing_method',
        ]
        read_only_fields = ['id', 'total_price']


class OrderItemCreateSerializer(serializers.ModelSerializer):
    """Сериализатор для создания позиции заказа."""

    class Meta:
        model = OrderItem
        fields = [
            'product',
            'quantity',
            'unit_price',
            'coffee_weight_grams',
            'coffee_form',
            'brewing_method',
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка заказов (компактный вид)."""

    customer_name = serializers.CharField(
        source='full_name',
        read_only=True,
        label='Имя клиента'
    )
    items_count = serializers.SerializerMethodField()
    status_badge_color = serializers.CharField(
        source='get_status_display',
        read_only=True,
        label='Цвет статуса'
    )

    class Meta:
        model = Order
        fields = [
            'id',
            'customer_name',
            'status',
            'total_amount',
            'payment_method',
            'delivery_method',
            'items_count',
            'created_at',
        ]

    def get_items_count(self, obj):
        return obj.items.count()


class OrderDetailSerializer(serializers.ModelSerializer):
    """Подробный сериализатор заказа с позициями."""

    items = OrderItemMinimalSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(
        source='full_name',
        read_only=True,
        label='Имя клиента'
    )

    class Meta:
        model = Order
        fields = [
            'id',
            'user',
            'customer_name',
            'status',
            'total_amount',
            'payment_method',
            'delivery_method',
            'first_name',
            'last_name',
            'phone',
            'email',
            'comment',
            'delivery_address',
            'delivery_date',
            'delivery_time',
            'delivery_cost',
            'yandex_order_id',
            'tracking_number',
            'delivery_status',
            'yookassa_payment_id',
            'reserved_at',
            'created_at',
            'updated_at',
            'items',
        ]
        read_only_fields = [
            'id',
            'user',
            'created_at',
            'updated_at',
            'yookassa_payment_id',
            'reserved_at',
        ]


class OrderCreateSerializer(serializers.Serializer):
    """Сериализатор для создания заказа."""

    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )
    delivery_method = serializers.ChoiceField(
        choices=['pickup', 'delivery']
    )
    payment_method = serializers.ChoiceField(
        choices=['online', 'cash']
    )
    delivery_address = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )
    delivery_date = serializers.DateTimeField(required=False, allow_null=True)
    delivery_time = serializers.TimeField(required=False, allow_null=True)
    items = OrderItemCreateSerializer(many=True)
    promo_code = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )


class OrderUpdateSerializer(serializers.Serializer):
    """Сериализатор для обновления статуса заказа."""

    status = serializers.ChoiceField(
        choices=[
            'new',
            'awaiting_payment',
            'in_progress',
            'ready',
            'delivered',
            'cancelled',
        ]
    )
    yandex_order_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )
    tracking_number = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )
    delivery_status = serializers.CharField(
        required=False,
        allow_blank=True,
        default=''
    )


class PromoCodeSerializer(serializers.ModelSerializer):
    """Сериализатор промокода."""

    is_valid = serializers.BooleanField(read_only=True, label='Актуален')
    remaining_uses = serializers.IntegerField(read_only=True, label='Осталось')
    discount_display = serializers.SerializerMethodField()

    class Meta:
        model = PromoCode
        fields = [
            'id',
            'code',
            'discount_type',
            'discount_value',
            'max_uses',
            'used_count',
            'remaining_uses',
            'is_active',
            'is_valid',
            'discount_display',
            'valid_from',
            'valid_to',
            'created_at',
        ]
        read_only_fields = ['id', 'used_count', 'created_at']

    def get_discount_display(self, obj):
        if obj.discount_type == 'percent':
            return f'{obj.discount_value}%'
        return f'{obj.discount_value} ₽'


class PromoCodeValidateSerializer(serializers.Serializer):
    """Сериализатор для валидации промокода."""

    code = serializers.CharField(max_length=50)

    def validate(self, attrs):
        code = attrs.get('code', '').strip()
        if not code:
            raise serializers.ValidationError('Промокод не указан')
        attrs['code'] = code
        return attrs
