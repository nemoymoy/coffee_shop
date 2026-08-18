from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Order, OrderItem, PromoCode


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product', 'quantity', 'unit_price', 'coffee_weight_grams',
                       'coffee_form', 'brewing_method']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'status_badge', 'full_name', 'phone', 'total_amount',
        'delivery_method', 'payment_method', 'created_at'
    ]
    list_filter = ['status', 'delivery_method', 'payment_method', 'created_at']
    search_fields = ['first_name', 'last_name', 'phone', 'email']
    readonly_fields = ['created_at', 'updated_at', 'yandex_access_token',
                       'yandex_order_id', 'tracking_number', 'delivery_status', 'delivery_cost']
    inlines = [OrderItemInline]
    actions = ['mark_awaiting_payment', 'mark_in_progress', 'mark_ready', 'mark_delivered', 'mark_cancelled', 'export_to_csv']

    date_hierarchy = 'created_at'
    list_per_page = 20

    fieldsets = (
        ('Customer info', {
            'fields': ('user', 'first_name', 'last_name', 'phone', 'email')
        }),
        ('Order', {
            'fields': ('status', 'total_amount', 'payment_method', 'delivery_method')
        }),
        ('Delivery', {
            'fields': ('delivery_address', 'delivery_date', 'delivery_time')
        }),
        ('Yandex Delivery info', {
            'fields': ('yandex_order_id', 'tracking_number', 'delivery_status', 'delivery_cost'),
            'classes': ('collapse',)
        }),
        ('Comment', {
            'fields': ('comment',)
        }),
        ('System', {
            'fields': ('created_at', 'updated_at', 'reserved_at', 'yookassa_payment_id'),
            'classes': ('collapse',)
        }),
    )

    def status_badge(self, obj):
        colors = {
            'new': '#1565c0',
            'awaiting_payment': '#f9a825',
            'in_progress': '#e65100',
            'ready': '#2e7d32',
            'delivered': '#00695c',
            'cancelled': '#c62828',
        }
        color = colors.get(obj.status, '#616161')
        return format_html(
            '<span style="background: {}; color: #fff; padding: 4px 12px; border-radius: 12px; font-size: 0.8em; font-weight: bold; white-space: nowrap;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def full_name(self, obj):
        return f'{obj.last_name} {obj.first_name}'
    full_name.short_description = 'Customer'

    def mark_awaiting_payment(self, request, queryset):
        count = queryset.filter(status='new').update(status='awaiting_payment')
        self.message_user(request, f'Updated: {count}')
    mark_awaiting_payment.short_description = 'Set to Awaiting Payment'

    def mark_in_progress(self, request, queryset):
        count = queryset.update(status='in_progress')
        self.message_user(request, f'Updated: {count}')
    mark_in_progress.short_description = 'Set to In Progress'

    def mark_ready(self, request, queryset):
        count = queryset.update(status='ready')
        self.message_user(request, f'Updated: {count}')
    mark_ready.short_description = 'Set to Ready'

    def mark_delivered(self, request, queryset):
        count = queryset.update(status='delivered')
        self.message_user(request, f'Updated: {count}')
    mark_delivered.short_description = 'Set to Delivered'

    def mark_cancelled(self, request, queryset):
        count = queryset.update(status='cancelled')
        self.message_user(request, f'Updated: {count}')
    mark_cancelled.short_description = 'Set to Cancelled'

    def export_to_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="orders.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Customer', 'Phone', 'Email', 'Status', 'Total',
                         'Delivery', 'Payment', 'Created'])
        for order in queryset:
            writer.writerow([
                order.id, f'{order.last_name} {order.first_name}',
                order.phone, order.email, order.get_status_display(),
                order.total_amount, order.get_delivery_method_display(),
                order.get_payment_method_display(), order.created_at
            ])
        self.message_user(request, f'Exported: {queryset.count()} orders')
        return response
    export_to_csv.short_description = 'Export CSV'


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'discount_type', 'discount_value', 'used_count',
        'max_uses', 'remaining_uses_badge', 'is_active', 'valid_period',
        'created_at'
    ]
    list_filter = ['is_active', 'discount_type', 'valid_from', 'valid_to']
    search_fields = ['code']
    readonly_fields = ['used_count', 'created_at', 'updated_at', 'remaining_uses']
    list_editable = ['is_active']
    list_per_page = 20

    def discount_display(self, obj):
        if obj.discount_type == 'percent':
            return f'{obj.discount_value}%'
        return f'{obj.discount_value} rub'
    discount_display.short_description = 'Discount'

    def remaining_uses_badge(self, obj):
        remaining = obj.remaining_uses
        if obj.max_uses == 0:
            return format_html('<span style="color: #2e7d32;">infinity</span>')
        elif remaining > 0:
            return format_html('<span style="color: #2e7d32;">{}</span>', remaining)
        else:
            return format_html('<span style="color: #c62828;">Expired</span>')
    remaining_uses_badge.short_description = 'Remaining'

    def valid_period(self, obj):
        now = timezone.now()
        if now < obj.valid_from:
            return format_html('<span style="color: #f9a825;">Not started</span>')
        elif now > obj.valid_to:
            return format_html('<span style="color: #c62828;">Expired</span>')
        elif obj.is_active:
            return format_html('<span style="color: #2e7d32;">Active</span>')
        else:
            return format_html('<span style="color: #616161;">Inactive</span>')
    valid_period.short_description = 'Validity'

    actions = ['activate_codes', 'deactivate_codes']

    def activate_codes(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f'Activated: {count}')
    activate_codes.short_description = 'Activate'

    def deactivate_codes(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f'Deactivated: {count}')
    deactivate_codes.short_description = 'Deactivate'


admin.site.site_header = 'Coffee Shop Admin'
admin.site.site_title = 'Coffee Shop Administration'
admin.site.index_title = 'Welcome to Coffee Shop Admin'
