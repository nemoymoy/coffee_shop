/**
 * Coffee Shop — AJAX корзина.
 * Заменяет стандартные POST-формы на AJAX-запросы,
 * обновляет счётчик в navbar и показывает toast-уведомления.
 */
var Cart = (function () {

    var ADD_URL = '/cart/add/';
    var REMOVE_URL = '/cart/remove/';

    /* ==================== Инициализация ==================== */

    /**
     * Запустить AJAX-режим корзины на странице каталога/деталей.
     */
    function init() {
        document.querySelectorAll('.js-add-to-cart').forEach(function (btn) {
            btn.addEventListener('click', handleAddToCart);
        });

        // Если есть табличная корзина — кнопки remove
        document.querySelectorAll('.js-cart-remove').forEach(function (btn) {
            btn.addEventListener('click', handleRemoveFromCart);
        });
    }

    /* ==================== Добавить в корзину ==================== */

    function handleAddToCart(e) {
        e.preventDefault();

        var btn = e.currentTarget;
        var formId = btn.getAttribute('data-form');
        var form = formId ? document.getElementById(formId) : btn.closest('form');

        if (!form) {
            CoffeeShop.showToast('Не удалось найти форму товара', 'danger');
            return;
        }

        // Собираем данные из формы
        var formData = new FormData(form);
        var data = {};
        formData.forEach(function (value, key) {
            data[key] = value;
        });

        btn.disabled = true;
        var originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

        CoffeeShop.postJson(ADD_URL, data)
            .then(function (response) {
                updateCartBadge(response.cart_count);
                CoffeeShop.showToast('Товар добавлен в корзину', 'success');
            })
            .catch(function (error) {
                if (error && error.redirect) {
                    window.location.href = error.redirect;
                } else {
                    var msg = error || 'Ошибка при добавлении';
                    if (error === 'login_required') {
                        msg = 'Войдите, чтобы добавить товар в корзину';
                    }
                    CoffeeShop.showToast(msg, 'danger');
                    window.location.href = error.redirect || '/accounts/login/';
                }
            })
            .finally(function () {
                btn.disabled = false;
                btn.innerHTML = originalText;
            });
    }

    /* ==================== Удалить из корзины ==================== */

    function handleRemoveFromCart(e) {
        e.preventDefault();

        var btn = e.currentTarget;
        var key = btn.getAttribute('data-key');
        var card = btn.closest('.cart-item-card');

        if (!key) {
            CoffeeShop.showToast('Не удалось определить товар', 'danger');
            return;
        }

        CoffeeShop.postJson(REMOVE_URL, {key: key})
            .then(function (response) {
                if (card) {
                    card.style.transition = 'opacity 0.3s';
                    card.style.opacity = '0';
                    setTimeout(function () {
                        card.remove();
                        recalcTotal();
                    }, 300);
                }
                updateCartBadge(response.cart_count);
                CoffeeShop.showToast('Товар удалён', 'info');

                // Если корзина пуста
                if (response.cart_count === 0) {
                    setTimeout(function () {
                        location.reload();
                    }, 500);
                }
            })
            .catch(function (error) {
                if (error && error.redirect) {
                    if (error.error === 'login_required') {
                        CoffeeShop.showToast('Войдите, чтобы удалить товар из корзины', 'warning');
                    }
                    window.location.href = error.redirect;
                } else {
                    CoffeeShop.showToast(error || 'Ошибка при удалении', 'danger');
                }
            });
    }

    /* ==================== Обновить счётчик ==================== */

    function updateCartBadge(count) {
        var badge = document.getElementById('cartBadge');
        if (!badge) return;

        if (count > 0) {
            badge.textContent = count;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    /* ==================== Пересчёт итогов ==================== */

    function recalcTotal() {
        var totalEl = document.getElementById('cartTotal');
        var rows = document.querySelectorAll('.cart-item-price');
        var total = 0;

        rows.forEach(function (row) {
            var val = parseFloat(row.textContent.replace(/\s/g, '').replace(',', '.'));
            if (!isNaN(val)) total += val;
        });

        if (totalEl) {
            totalEl.textContent = CoffeeShop.formatPrice(total);
        }
    }

    /* ==================== Export ==================== */

    return {
        init: init
    };

})();

// Автоинициализация при загрузке DOM
document.addEventListener('DOMContentLoaded', Cart.init);
