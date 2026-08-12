/**
 * Coffee Shop — Coffee Selector.
 * Пошаговый выбор: вес → форма → способ заваривания.
 * Автопересчёт цены, валидация в реальном времени.
 */
var CoffeeSelector = (function () {

    /* ==================== Инициализация ==================== */

    function init() {
        // Находим все секции кофе на странице
        document.querySelectorAll('.coffee-selector').forEach(initSingleSelector);
    }

    function initSingleSelector(container) {
        var weightSelect = container.querySelector('.coffee-weight');
        var formRadios = container.querySelectorAll('.coffee-form-input');
        var brewingBlock = container.querySelector('.coffee-brewing-block');
        var brewingSelect = container.querySelector('.coffee-brewing-method');
        var priceDisplay = container.querySelector('.coffee-price-display');
        var submitBtn = container.querySelector('.coffee-submit-btn');
        var weightInfo = container.querySelector('.coffee-weight-info');
        var availWeightsData = container.getAttribute('data-weights');
        var productId = container.getAttribute('data-product-id');

        if (!weightSelect) return;

        var availableWeights = availWeightsData ? JSON.parse(availWeightsData) : [];
        var pricePer50 = parseFloat(container.getAttribute('data-price-per-50g')) || 0;

        /* ---- State ---- */
        var state = {
            weight: 0,
            form: 'beans',
            brewingMethod: null,
            isCoffee: container.getAttribute('data-is-coffee') === '1',
            isOutOfStock: container.getAttribute('data-out-of-stock') === 'true',
        };

        /* ---- Weight ---- */
        if (availableWeights.length > 0) {
            weightSelect.innerHTML = '';
            availableWeights.forEach(function (w) {
                var opt = document.createElement('option');
                opt.value = w;
                opt.textContent = w + ' г';
                weightSelect.appendChild(opt);
            });

            var firstWeight = availableWeights[0];
            weightSelect.value = firstWeight;
            state.weight = parseInt(firstWeight);
            recalcPrice();
        } else {
            weightSelect.disabled = true;
            var optDisabled = document.createElement('option');
            optDisabled.textContent = 'Нет в наличии';
            weightSelect.appendChild(optDisabled);
            submitBtn.disabled = true;
        }

        /* ---- Form (beans/ground) ---- */
        formRadios.forEach(function (radio) {
            radio.addEventListener('change', function () {
                state.form = this.value;
                if (state.form === 'ground') {
                    if (brewingBlock) brewingBlock.style.display = 'block';
                } else {
                    if (brewingBlock) brewingBlock.style.display = 'none';
                    state.brewingMethod = null;
                }
                showWeightInfo(state.weight);
            });
        });

        /* ---- Brewing method ---- */
        if (brewingSelect) {
            brewingSelect.addEventListener('change', function () {
                state.brewingMethod = this.value;
            });
        }

        /* ---- Events ---- */
        weightSelect.addEventListener('change', function () {
            state.weight = parseInt(this.value);
            recalcPrice();
            showWeightInfo(state.weight);
        });

        /* ---- Init state ---- */
        if (weightSelect.value) {
            state.weight = parseInt(weightSelect.value);
            recalcPrice();
        }
        if (brewingBlock) brewingBlock.style.display = 'none';

        /* ---- Helper functions ---- */
        function recalcPrice() {
            if (!state.isCoffee || state.weight <= 0) {
                priceDisplay.textContent = state.isOutOfStock ? 'Нет в наличии' : '—';
                submitBtn.disabled = true;
                return;
            }

            var price = (state.weight / 50) * pricePer50;
            priceDisplay.textContent = CoffeeShop.formatPrice(price) + ' ₽';
            submitBtn.disabled = false;
        }

        function showWeightInfo(weight) {
            if (weightInfo) {
                var label = state.form === 'ground' ? 'молотый' : 'в зёрнах';
                var info = weight + ' г, ' + label;
                if (state.brewingMethod) {
                    info += ' · ' + getBrewingMethodLabel(state.brewingMethod);
                }
                weightInfo.textContent = info;
            }
        }

        function getBrewingMethodLabel(value) {
            if (!brewingSelect) return value;
            for (var i = 0; i < brewingSelect.options.length; i++) {
                if (brewingSelect.options[i].value === value) {
                    return brewingSelect.options[i].textContent;
                }
            }
            return value;
        }

        /* ---- Submit via AJAX ---- */
        if (submitBtn) {
            submitBtn.addEventListener('click', function () {
                if (!state.isCoffee) return;

                // Валидация: молотый → способ заваривания обязателен
                if (state.form === 'ground' && !state.brewingMethod) {
                    CoffeeShop.showToast('Выберите способ заваривания', 'warning');
                    if (brewingBlock) brewingBlock.style.display = 'block';
                    if (brewingSelect) brewingSelect.focus();
                    return;
                }

                // Отправка через AJAX
                sendToCart();
            });
        }

        /* ---- Отправка в корзину ---- */
        function sendToCart() {
            var ADD_URL = '/cart/add/';
            var data = {
                'product_id': productId,
                'weight': state.weight,
                'coffee_form': state.form,
            };
            if (state.brewingMethod) {
                data.brewing_method = state.brewingMethod;
            }

            var originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Добавляется...';

            CoffeeShop.postJson(ADD_URL, data)
                .then(function (response) {
                    CoffeeShop.showToast('Товар добавлен в корзину', 'success');
                    updateCartBadge(response.cart_count);
                    // Перезагрузка страницы для обновления остатка
                    setTimeout(function () {
                        location.reload();
                    }, 800);
                })
                .catch(function (error) {
                    CoffeeShop.showToast(error || 'Ошибка при добавлении в корзину', 'danger');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                });
        }

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
    }

    /* ==================== Export ==================== */

    return {
        init: init
    };

})();

document.addEventListener('DOMContentLoaded', CoffeeSelector.init);
