/**
 * Coffee Shop — AJAX корзина.
 * Заменяет стандартные POST-формы на AJAX-запросы,
 * обновляет счётчик в navbar и показывает toast-уведомления.
 */
var Cart = (function () {

    var ADD_URL = '/cart/add/';
    var REMOVE_URL = '/cart/remove/';
    var UPDATE_URL = '/cart/update/';

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

        // Спиннеры количества на странице корзины
        document.querySelectorAll('.js-quantity-increase').forEach(function (btn) {
            btn.addEventListener('click', handleQuantityChange);
        });
        document.querySelectorAll('.js-quantity-decrease').forEach(function (btn) {
            btn.addEventListener('click', handleQuantityChange);
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

        // Debug: log form data
        console.log('[cart.js] Form data:', data);
        console.log('[cart.js] CSRF token in data:', data.csrfmiddlewaretoken || 'MISSING');

        btn.disabled = true;
        var originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

        CoffeeShop.postJson(ADD_URL, data)
            .then(function (response) {
                updateCartBadge(response.cart_count);
                CoffeeShop.showToast('Товар добавлен в корзину', 'success');
            })
            .catch(function (error) {
                console.log('[cart.js] Error adding to cart:', error);
                if (error && error.error === 'email_not_verified') {
                    CoffeeShop.showToast(error.message || 'Необходимо подтвердить email', 'warning');
                    if (error.redirect) {
                        window.location.href = error.redirect;
                    }
                } else if (error && error.redirect) {
                    CoffeeShop.showToast('Войдите, чтобы добавить товар в корзину', 'warning');
                    window.location.href = error.redirect;
                } else {
                    CoffeeShop.showToast(error || 'Ошибка при добавлении', 'danger');
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
                    CoffeeShop.showToast('Войдите, чтобы удалить товар из корзины', 'warning');
                    window.location.href = error.redirect;
                } else {
                    CoffeeShop.showToast(error || 'Ошибка при удалении', 'danger');
                }
            });
    }

    /* ==================== Изменение количества ==================== */

    function handleQuantityChange(e) {
        e.preventDefault();

        var btn = e.currentTarget;
        var isIncrease = btn.classList.contains('js-quantity-increase');
        var spinner = btn.closest('.js-quantity-spinner');
        var key = spinner.getAttribute('data-cart-key');
        var productType = spinner.getAttribute('data-product-type');
        var stockUnit = spinner.getAttribute('data-stock-unit');
        var availableStock = parseInt(spinner.getAttribute('data-available-stock'), 10);
        var input = spinner.querySelector('.js-quantity-value');
        var currentQuantity = parseInt(input.value, 10);

        if (!key || isNaN(availableStock) || isNaN(currentQuantity)) {
            CoffeeShop.showToast('Не удалось определить товар', 'danger');
            return;
        }

        var step = (stockUnit === 'g') ? 50 : 1;
        var minQty = (stockUnit === 'g') ? 50 : 1;
        var newQuantity = isIncrease ? currentQuantity + step : currentQuantity - step;

        console.log('[cart.js] Product type:', productType, 'currentQty:', currentQuantity, 'newQty:', newQuantity, 'availableStock:', availableStock, 'step:', step);

        // Проверка границ
        if (newQuantity < minQty) {
            console.log('[cart.js] Below minimum:', minQty);
            return;
        }
        if (newQuantity > availableStock) {
            console.log('[cart.js] Above available:', availableStock);
            CoffeeShop.showToast('Достигнут лимит остатка на складе', 'warning');
            return;
        }

        // Блокируем кнопки на время запроса
        btn.disabled = true;
        var decreaseBtn = spinner.querySelector('.js-quantity-decrease');
        var increaseBtn = spinner.querySelector('.js-quantity-increase');
        decreaseBtn.disabled = true;
        increaseBtn.disabled = true;

        CoffeeShop.postJson(UPDATE_URL, {key: key, quantity: newQuantity})
            .then(function (response) {
                console.log('[cart.js] Update response:', response);
                // Обновляем значение в инпуте
                input.value = newQuantity;
                // Обновляем key на спиннере
                var newKey = response.new_key || key;
                spinner.setAttribute('data-cart-key', newKey);
                // Обновляем key на карточке товара
                var card = spinner.closest('.cart-item-card');
                if (card) {
                    card.setAttribute('data-cart-key', newKey);
                    // Обновляем key на кнопке удаления
                    var removeBtn = card.querySelector('.js-cart-remove');
                    if (removeBtn) {
                        removeBtn.setAttribute('data-key', newKey);
                    }
                    // Обновляем цену в плитке
                    var priceEl = card.querySelector('.cart-item-price');
                    if (priceEl) {
                        console.log('[cart.js] new_price:', response.new_price, 'type:', typeof response.new_price);
                        priceEl.textContent = CoffeeShop.formatPrice(response.new_price);
                    }
                    // Обновляем параметры товара (вес/форма/способ заваривания)
                    var paramsEl = card.querySelector('.cart-item-params');
                    if (paramsEl) {
                        var stockUnit = spinner.getAttribute('data-stock-unit');
                        var coffeeForm = card.getAttribute('data-coffee-form');
                        var brewingLabel = card.getAttribute('data-brewing-method-label');
                        var paramsText = '';
                        if (stockUnit === 'g') {
                            // Кофе: вес + форма + способ заваривания
                            paramsText = newQuantity + ' г';
                            if (coffeeForm === 'ground') {
                                paramsText += ' · молотый';
                            } else {
                                paramsText += ' · в зёрнах';
                            }
                            if (brewingLabel) {
                                paramsText += ' · ' + brewingLabel;
                            }
                        } else {
                            // Не кофе: общий вес = вес одного товара * количество
                            var productWeight = parseInt(card.getAttribute('data-product-weight-grams'), 10);
                            if (productWeight && productWeight > 0) {
                                paramsText = (productWeight * newQuantity) + ' г';
                            } else {
                                paramsText = newQuantity + ' шт';
                            }
                        }
                        paramsEl.textContent = paramsText;
                    }
                }
                // Обновляем счётчик в бейдже
                updateCartBadge(response.cart_count);
                // Пересчитываем итог
                recalcTotal();
                CoffeeShop.showToast('Количество обновлено', 'success');
            })
            .catch(function (error) {
                CoffeeShop.showToast(error || 'Ошибка при обновлении', 'danger');
            })
            .finally(function () {
                btn.disabled = false;
                decreaseBtn.disabled = false;
                increaseBtn.disabled = false;
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
