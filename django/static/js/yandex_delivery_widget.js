/**
 * Coffee Shop — Yandex Delivery Widget (Cargo API).
 *
 * Simplified widget using Yandex Delivery widget integration:
 * 1. Show PVZ/terminal selector via Yandex widget
 * 2. On PVZ selection → store coords, address, PVZ ID
 * 3. Calculate delivery cost via backend API
 * 4. Update checkout form with delivery info
 */
var YaDelivery = (function () {

    /* ==================== State & Constants ==================== */

    var state = {
        widgetInitialized: false,
        selectedPoint: null,
        estimatedCost: null
    };

    /* ==================== Init ==================== */

    function init() {
        var container = document.getElementById('delivery-widget');
        if (!container) {
            console.warn('[YaDelivery] Container #delivery-widget not found');
            return;
        }

        // Wait for Yandex widget to load
        if (window.YaDelivery) {
            startWidget();
        } else {
            document.addEventListener('YaNddWidgetLoad', startWidget);
        }

        state.widgetInitialized = true;
    }

    /* ==================== Widget Setup ==================== */

    function startWidget() {
        try {
            window.YaDelivery.createWidget({
                containerId: 'delivery-widget',
                city: 'samara',
                type: ['pickup_point', 'terminal'],
                onSelect: function(point) {
                    handlePointSelected(point);
                }
            });
        } catch (e) {
            console.error('[YaDelivery] Failed to create widget:', e);
            showError('Не удалось загрузить виджет доставки');
        }
    }

    /* ==================== Point Selection ==================== */

    function handlePointSelected(point) {
        // point.id — идентификатор пункта в системе Яндекс Доставки
        // point.address — адрес пункта
        // point.coordinates — [долгота, широта]

        state.selectedPoint = point;

        // Update hidden form fields
        setFieldValue('pvz_id', point.id || '');
        setFieldValue('pvz_address', point.address || '');
        setFieldValue('delivery_coords', point.coordinates ? point.coordinates.join(',') : '');
        setFieldValue('delivery_address', point.address || '');

        // Validate coordinates
        if (!point.coordinates) {
            showError('Не удалось определить координаты доставки. Попробуйте выбрать пункт заново.');
            blockCheckout(true);
            return;
        }

        blockCheckout(false);

        // Calculate delivery cost via AJAX
        showEstimatedCost(point);
    }

    /* ==================== Cost Calculation ==================== */

    function showEstimatedCost(point) {
        var costEl = document.getElementById('delivery-cost');

        if (costEl) {
            costEl.textContent = 'Расчёт...';
        }

        fetch('/checkout/calculate-delivery/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                destination_coords: point.coordinates,
                destination_address: point.address,
                pvz_id: point.id || null,
                delivery_type: 'pickup'
            })
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success) {
                state.estimatedCost = data.price;
                if (costEl) {
                    costEl.textContent = data.price + ' ' + (data.currency || 'RUB');
                }

                // Update order summary
                updateOrderSummary(data.price);
            } else {
                if (costEl) {
                    costEl.textContent = 'Ошибка расчёта';
                }
                showError(data.error || 'Не удалось рассчитать стоимость доставки');
            }
        })
        .catch(function(err) {
            console.error('[YaDelivery] Calculate cost error:', err);
            if (costEl) {
                costEl.textContent = 'Ошибка подключения';
            }
            showError('Ошибка подключения к серверу');
        });
    }

    /* ==================== UI Helpers ==================== */

    function showError(message) {
        var errorDiv = document.getElementById('delivery-error');
        if (errorDiv) {
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
        }
    }

    function blockCheckout(block) {
        var btn = document.getElementById('checkout-btn');
        if (btn) {
            btn.disabled = block;
        }
    }

    function updateOrderSummary(price) {
        var costSpan = document.getElementById('orderDeliveryCost');
        var totalSpan = document.getElementById('orderTotal');

        if (costSpan) {
            costSpan.textContent = formatPrice(price) + ' ₽';
        }

        // Recalculate total if Checkout utility is available
        if (typeof CoffeeShop !== 'undefined' && CoffeeShop.formatPrice) {
            // Try to find the cart total element and recalculate
            var cartTotalEl = document.getElementById('cartTotal') || document.getElementById('orderTotal');
            if (cartTotalEl) {
                var itemsTotal = parseFloat(cartTotalEl.textContent.replace(/[^\d.]/g, '')) || 0;
                var newTotal = itemsTotal + parseFloat(price) || itemsTotal;
                cartTotalEl.textContent = formatPrice(newTotal) + ' ₽';
            }
        }
    }

    function formatPrice(price) {
        return parseFloat(price).toLocaleString('ru-RU', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });
    }

    /* ==================== Form Helpers ==================== */

    function setFieldValue(fieldId, value) {
        var field = document.getElementById(fieldId);
        if (field) {
            field.value = value;
        }
    }

    function getCsrfToken() {
        var tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenInput) {
            return tokenInput.value;
        }
        // Fallback: extract from cookie
        var name = 'csrftoken';
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue || '';
    }

    /* ==================== Export ==================== */

    return {
        init: init,
        getSelectedPoint: function() { return state.selectedPoint; },
        getEstimatedCost: function() { return state.estimatedCost; }
    };

})();

document.addEventListener('DOMContentLoaded', YaDelivery.init);
