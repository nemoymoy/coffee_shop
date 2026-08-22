/**
 * Coffee Shop — Checkout.
 * Валидация формы оформления заказа, переключение способа получения,
 * расчёт стоимости доставки через Яндекс Доставку.
 */
var Checkout = (function () {

    /* ==================== Вспомогательные функции ==================== */

    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function debounce(func, wait) {
        var timeout;
        return function () {
            var context = this;
            var args = arguments;
            clearTimeout(timeout);
            timeout = setTimeout(function () {
                func.apply(context, args);
            }, wait);
        };
    }

    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (
                    cookie.substring(0, name.length + 1) ===
                    name + '='
                ) {
                    cookieValue = decodeURIComponent(
                        cookie.substring(name.length + 1)
                    );
                    break;
                }
            }
        }
        return cookieValue;
    }


    /* ==================== Delivery Summary ==================== */

    function updateDeliverySummary() {
        var deliverySummary = document.getElementById('deliverySummary');
        if (!deliverySummary) return;

        var addressInput = document.getElementById('id_delivery_address');
        var addressValue = addressInput ? addressInput.value.trim() : '';
        if (!addressValue) {
            deliverySummary.style.display = 'none';
            return;
        }

        var summaryType = document.getElementById('summaryType');
        var summaryAddress = document.getElementById('summaryAddress');
        var summaryCost = document.getElementById('summaryCost');
        var summaryEta = document.getElementById('summaryEta');
        var deliveryCostEl = document.getElementById('deliveryCost');
        var deliveryEtaEl = document.getElementById('deliveryEta');

        var selectedType = null;
        if (window.YandexDeliveryWidget && window.YandexDeliveryWidget.getSelectedType) {
            selectedType = window.YandexDeliveryWidget.getSelectedType();
        }
        var typeLabel = {
            courier: '🚗 Курьер',
            pvz: '📦 Пункт выдачи (ПВЗ)',
            postomat: '📮 Постомат'
        }[selectedType || 'courier'] || 'Delivery';

        if (summaryType) summaryType.textContent = typeLabel;
        if (summaryAddress) summaryAddress.textContent = addressValue;
        if (summaryCost) summaryCost.textContent = deliveryCostEl ? deliveryCostEl.textContent : '—';
        if (summaryEta) summaryEta.textContent = deliveryEtaEl ? deliveryEtaEl.textContent : '';

        deliverySummary.style.display = 'block';
    }

    /* ==================== Инициализация ==================== */

    function init() {
        var form = document.querySelector('.checkout-form');
        if (!form) return;

        var phoneInput = form.querySelector('#id_phone');
        var emailInput = form.querySelector('#id_email');
        var firstNameInput = form.querySelector('#id_first_name');
        var lastNameInput = form.querySelector('#id_last_name');
        var addressInput = form.querySelector('#id_delivery_address');
        var deliveryInputs = form.querySelectorAll('input[name="delivery_method"]');
        var addressBlock = document.getElementById('addressBlock');
        var submitBtn = form.querySelector('button[type="submit"]');
        var totalEl = document.getElementById('checkoutTotal');

        var deliveryCalculationTimeout = null;
        var deliveryCalculationDebounced = null;

        /* ---- Phone formatting ---- */
        if (phoneInput) {
            phoneInput.addEventListener('input', function () {
                var raw = this.value.replace(/^(\+)?(?=8|7)/, '');
                var formatted = CoffeeShop.formatPhone(raw);
                this.value = formatted;
            });
        }

        /* ---- Address input ---- */
        if (addressInput) {
            addressInput.addEventListener('input', function () {
                var value = this.value.trim();
                var isDeliveryChecked = form.querySelector('input[name="delivery_method"][value="delivery"]:checked');
                if (value) {
                    updateDeliverySummary();
                    if (isDeliveryChecked) {
                        calculateDeliveryPrice();
                    }
                }
            });
        }


    /* ---- Email validation ---- */
        if (emailInput) {
            emailInput.addEventListener('blur', function () {
                if (this.value && !isValidEmail(this.value)) {
                    this.classList.add('is-invalid');
                    var feedback = this.nextElementSibling;
                    if (feedback && feedback.classList.contains('invalid-feedback')) {
                        feedback.style.display = 'block';
                    }
                } else {
                    this.classList.remove('is-invalid');
                    this.classList.add('is-valid');
                }
            });
        }

        /* ---- Delivery price calculation ---- */
        function calculateDeliveryPrice() {
            var deliveryAddressInput = addressInput;
            var deliveryCostEl = document.getElementById('deliveryCost');
            var deliveryEtaEl = document.getElementById('deliveryEta');

            if (!deliveryAddressInput || !deliveryCostEl || !deliveryEtaEl) {
                return;
            }

            var addressValue = deliveryAddressInput.value.trim();
            if (!addressValue) {
                deliveryCostEl.textContent = '—';
                deliveryEtaEl.textContent = '—';
                return;
            }

            // Parse address into city/street/house
            var address = parseAddress(addressValue);
            if (!address.city || !address.street || !address.house) {
                return;
            }

            // Show loading
            deliveryCostEl.textContent = 'Расчёт...';
            deliveryEtaEl.textContent = '';

            // Debounce the request
            if (deliveryCalculationTimeout) {
                clearTimeout(deliveryCalculationTimeout);
            }
            deliveryCalculationTimeout = setTimeout(function () {
                fetch('/checkout/calculate-delivery/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                    },
                    body: JSON.stringify({
                        city: address.city,
                        street: address.street,
                        house: address.house,
                        apartment: address.apartment,
                    }),
                })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data.success && data.price) {
                        deliveryCostEl.textContent =
                            CoffeeShop.formatPrice(data.price) + ' ₽';
                        deliveryEtaEl.textContent = data.eta || '';
                        updateDeliverySummary();
                    } else {
                        // Fallback: show default price
                        deliveryCostEl.textContent = '299 ₽';
                        deliveryEtaEl.textContent = '30-45 мин';
                        updateDeliverySummary();
                    }
                })
                .catch(function () {
                    // Fallback on error
                    deliveryCostEl.textContent = '299 ₽';
                    deliveryEtaEl.textContent = '30-45 мин';
                });
            }, 1500);
        }

        /* Parse address string into structured data */
        function parseAddress(raw) {
            var result = {
                city: '',
                street: '',
                house: '',
                apartment: '',
            };
            var parts = raw.split(',').map(function (s) { return s.trim(); });

            // Format: "Город, улица, дом, кв"
            if (parts.length >= 1) {
                result.city = parts[0];
            }
            if (parts.length >= 2) {
                result.street = parts[1];
            }
            if (parts.length >= 3) {
                var parts3 = parts[2].split('-');
                result.house = parts3[0].trim();
                if (parts3.length > 1) {
                    result.apartment = parts3[1].trim();
                }
            }

            return result;
        }

        /* ---- Delivery method toggle ---- */
        function updateAddressBlock() {
            var checked = form.querySelector('input[name="delivery_method"][value="delivery"]:checked');
            if (checked) {
                if (addressBlock) addressBlock.style.display = 'block';
                if (addressInput) addressInput.setAttribute('required', 'required');
                // Show delivery info block
                var deliveryInfoBlock = document.getElementById('deliveryInfoBlock');
                if (deliveryInfoBlock) {
                    deliveryInfoBlock.style.display = 'block';
                }
                // Trigger delivery price calculation (if address is already set)
                if (addressInput && addressInput.value.trim()) {
                    calculateDeliveryPrice();
                    updateDeliverySummary();
                }
            } else {
                if (addressBlock) addressBlock.style.display = 'none';
                if (addressInput) {
                    addressInput.removeAttribute('required');
                    addressInput.value = '';
                }
                // Hide delivery info
                var deliveryInfoBlock = document.getElementById('deliveryInfoBlock');
                if (deliveryInfoBlock) {
                    deliveryInfoBlock.style.display = 'none';
                }
                // Hide delivery summary
                var deliverySummary = document.getElementById('deliverySummary');
                if (deliverySummary) {
                    deliverySummary.style.display = 'none';
                }
                // Reset delivery info
                var deliveryCostEl = document.getElementById('deliveryCost');
                var deliveryEtaEl = document.getElementById('deliveryEta');
                if (deliveryCostEl) deliveryCostEl.textContent = '—';
                if (deliveryEtaEl) deliveryEtaEl.textContent = '—';
            }
        }


        if (deliveryInputs && deliveryInputs.length) {
            deliveryInputs.forEach(function (radio) {
                radio.addEventListener('change', updateAddressBlock);
            });
            // Init
            updateAddressBlock();
        }

        /* ---- Yandex Delivery Widget integration ---- */
        // При выборе radio "Доставка" — автоматически открываем виджет
        if (deliveryInputs && deliveryInputs.length && window.YandexDeliveryWidget) {
            deliveryInputs.forEach(function (radio) {
                if (radio.value === 'delivery' && radio.checked) {
                    // Виджет уже открыт при загрузке, если выбрана доставка
                    setTimeout(function() {
                        YandexDeliveryWidget.openModal();
                    }, 300);
                }
                radio.addEventListener('change', function () {
                    if (this.checked && this.value === 'delivery') {
                        // Автоматически открываем виджет
                        setTimeout(function() {
                            YandexDeliveryWidget.openModal();
                        }, 200);
                    }
                });
            });
        }

        /* ---- Debounced required fields ---- */
        [firstNameInput, lastNameInput].forEach(function (input) {
            if (input) {
                input.addEventListener('input', debounce(function () {
                    if (this.value.trim().length >= 2) {
                        this.classList.remove('is-invalid');
                        this.classList.add('is-valid');
                    }
                }, 300));
            }
        });

        /* ---- Submit validation ---- */
        if (submitBtn) {
            submitBtn.addEventListener('click', function (e) {
                var isValid = true;

                // Required fields
                form.querySelectorAll('[required]').forEach(function (input) {
                    if (!input.value.trim()) {
                        isValid = false;
                        input.classList.add('is-invalid');
                        if (input.classList.contains('form-control')) {
                            input.focus();
                            return false; // stop on first
                        }
                    } else {
                        input.classList.remove('is-invalid');
                        input.classList.add('is-valid');
                    }
                });

                // Email validation
                if (emailInput && emailInput.value && !isValidEmail(emailInput.value)) {
                    isValid = false;
                    emailInput.classList.add('is-invalid');
                    emailInput.focus();
                }

                // Phone validation
                if (phoneInput) {
                    var digits = phoneInput.value.replace(/\D/g, '');
                    if (digits.length < 11) {
                        isValid = false;
                        phoneInput.classList.add('is-invalid');
                        if (isValid) phoneInput.focus();
                    }
                }

                if (!isValid) {
                    e.preventDefault();
                    CoffeeShop.showToast('Заполните все обязательные поля', 'warning');
                }
            });
        }

        /* ---- Total display ---- */
        if (totalEl) {
            // Переводим цену из числа в форматированный вид
            var rawTotal = totalEl.getAttribute('data-total');
            if (rawTotal) {
                totalEl.textContent = CoffeeShop.formatPrice(rawTotal) + ' ₽';
            }
        }
    }

    /* ==================== Export ==================== */

    return {
        init: init,
        updateDeliverySummary: updateDeliverySummary
    };

})();

document.addEventListener('DOMContentLoaded', Checkout.init);
