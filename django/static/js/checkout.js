/**
 * Coffee Shop — Checkout.
 * Валидация формы оформления заказа, переключение способа получения,
 * расчёт стоимости доставки через Яндекс Доставку.
 */
var Checkout = (function () {

    /* ==================== Конфигурация ==================== */

    var CONFIG = {
        DELIVERY_CALCULATION_URL: '/checkout/calculate-delivery/',
        DELIVERY_CALCULATION_DEBOUNCE_MS: 1500,
        NAME_DEBOUNCE_MS: 300,
        YANDEX_WIDGET_OPEN_DELAY_MS: 200,
        MIN_NAME_LENGTH: 2,
        MIN_PHONE_DIGITS: 11,
        DEFAULT_DELIVERY_PRICE: 299,
        DEFAULT_DELIVERY_ETA: '30-45 мин',
        DELIVERY_SUMMARY_TYPES: {
            courier: '🚗 Курьер',
            pvz: '📦 Пункт выдачи (ПВЗ)',
            postomat: '📮 Постомат'
        }
    };

    /* ==================== Состояние ==================== */

    var _elements = {};
    var _deliveryCalculationTimeout = null;

    /* ==================== Приватные утилиты ==================== */

    /**
     * Валидация email по regex.
     */
    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    /**
     * Кэширование DOM-элементов формы.
     */
    function _cacheElements(form) {
        _elements = {
            form: form,
            phone: form.querySelector('#id_phone'),
            email: form.querySelector('#id_email'),
            firstName: form.querySelector('#id_first_name'),
            lastName: form.querySelector('#id_last_name'),
            address: form.querySelector('#id_delivery_address'),
            deliveryRadios: form.querySelectorAll('input[name="delivery_method"]'),
            submitBtn: form.querySelector('button[type="submit"]')
        };
        _elements.deliveryInfoBlock = document.getElementById('deliveryInfoBlock');
        _elements.deliverySummary = document.getElementById('deliverySummary');
        _elements.addressBlock = document.getElementById('addressBlock');
        _elements.summaryType = document.getElementById('summaryType');
        _elements.summaryAddress = document.getElementById('summaryAddress');
        _elements.summaryCost = document.getElementById('summaryCost');
        _elements.summaryEta = document.getElementById('summaryEta');
        _elements.deliveryCost = document.getElementById('deliveryCost');
        _elements.deliveryEta = document.getElementById('deliveryEta');
        _elements.total = document.getElementById('checkoutTotal');
    }

    /**
     * Расчёт стоимости доставки с debounce.
     */
    function _calculateDeliveryPrice() {
        var addressValue = _elements.address ? _elements.address.value.trim() : '';

        if (!addressValue) {
            _setDeliveryPlaceholder();
            return;
        }

        var address = CoffeeShop.parseAddress(addressValue);
        if (!address.city || !address.street || !address.house) {
            return;
        }

        _setDeliveryLoading();

        if (_deliveryCalculationTimeout) {
            clearTimeout(_deliveryCalculationTimeout);
        }

        _deliveryCalculationTimeout = setTimeout(function () {
            fetch(CONFIG.DELIVERY_CALCULATION_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': CoffeeShop.getCookie('csrftoken')
                },
                body: JSON.stringify({
                    city: address.city,
                    street: address.street,
                    house: address.house,
                    apartment: address.apartment
                })
            })
            .then(function (response) { return response.json(); })
            .then(function (data) {
                if (data.success && data.price) {
                    _setDeliveryResult(data.price, data.eta);
                } else {
                    _setDeliveryFallback();
                }
            })
            .catch(function () {
                _setDeliveryFallback();
            });
        }, CONFIG.DELIVERY_CALCULATION_DEBOUNCE_MS);
    }

    /**
     * Обновление сводки доставки.
     */
    function _updateDeliverySummary(selectedTypeOverride) {
        var summary = _elements.deliverySummary;
        if (!summary) return;

        var addressValue = _elements.address ? _elements.address.value.trim() : '';
        var isDeliveryChecked = _elements.form
            ? _elements.form.querySelector('input[name="delivery_method"][value="delivery"]:checked')
            : null;

        if (!addressValue || !isDeliveryChecked) {
            summary.style.display = 'none';
            return;
        }

        var selectedType = selectedTypeOverride || null;
        if (!selectedType && window.YandexDeliveryWidget && window.YandexDeliveryWidget.getSelectedType) {
            selectedType = window.YandexDeliveryWidget.getSelectedType();
        }

        var typeLabel = CONFIG.DELIVERY_SUMMARY_TYPES[selectedType || 'courier'] || CONFIG.DELIVERY_SUMMARY_TYPES.courier;

        _elements.summaryType.textContent = typeLabel;
        _elements.summaryAddress.textContent = addressValue;
        _elements.summaryCost.textContent = _elements.deliveryCost ? _elements.deliveryCost.textContent : (CONFIG.DEFAULT_DELIVERY_PRICE + ' ₽');
        _elements.summaryEta.textContent = _elements.deliveryEta ? _elements.deliveryEta.textContent : '';

        summary.style.display = 'block';
    }

    /**
     * Переключение блока адреса при смене способа доставки.
     */
    function _updateAddressBlock() {
        var isDeliveryChecked = _elements.form
            ? _elements.form.querySelector('input[name="delivery_method"][value="delivery"]:checked')
            : null;

        if (isDeliveryChecked) {
            _showDeliveryBlock();
        } else {
            _hideDeliveryBlock();
        }
    }

    /* ==================== Вспомогательные функции доставки ==================== */

    function _showDeliveryBlock() {
        if (_elements.addressBlock) {
            _elements.addressBlock.style.display = 'block';
        }
        if (_elements.address) {
            _elements.address.setAttribute('required', 'required');
        }
        if (_elements.deliveryInfoBlock) {
            _elements.deliveryInfoBlock.style.display = 'block';
        }
        if (_elements.address && _elements.address.value.trim()) {
            _calculateDeliveryPrice();
            _updateDeliverySummary();
        }
    }

    function _hideDeliveryBlock() {
        if (_elements.addressBlock) {
            _elements.addressBlock.style.display = 'none';
        }
        if (_elements.address) {
            _elements.address.removeAttribute('required');
            _elements.address.value = '';
        }
        if (_elements.deliveryInfoBlock) {
            _elements.deliveryInfoBlock.style.display = 'none';
        }
        if (_elements.deliverySummary) {
            _elements.deliverySummary.style.display = 'none';
        }
        _setDeliveryPlaceholder();
    }

    function _setDeliveryPlaceholder() {
        if (_elements.deliveryCost) _elements.deliveryCost.textContent = '—';
        if (_elements.deliveryEta) _elements.deliveryEta.textContent = '—';
    }

    function _setDeliveryLoading() {
        if (_elements.deliveryCost) _elements.deliveryCost.textContent = 'Расчёт...';
        if (_elements.deliveryEta) _elements.deliveryEta.textContent = '';
    }

    function _setDeliveryResult(price, eta) {
        if (_elements.deliveryCost) {
            _elements.deliveryCost.textContent = CoffeeShop.formatPrice(price) + ' ₽';
        }
        if (_elements.deliveryEta) {
            _elements.deliveryEta.textContent = eta || '';
        }
        _updateDeliverySummary();
    }

    function _setDeliveryFallback() {
        if (_elements.deliveryCost) {
            _elements.deliveryCost.textContent = CONFIG.DEFAULT_DELIVERY_PRICE + ' ₽';
        }
        if (_elements.deliveryEta) {
            _elements.deliveryEta.textContent = CONFIG.DEFAULT_DELIVERY_ETA;
        }
        _updateDeliverySummary();
    }

    /* ==================== Инициализация компонентов ==================== */

    /**
     * Форматирование телефона при вводе.
     */
    function _initPhoneFormatting() {
        var phone = _elements.phone;
        if (!phone) return;

        phone.addEventListener('input', function () {
            var raw = this.value.replace(/^(\+)?(?=8|7)/, '');
            this.value = CoffeeShop.formatPhone(raw);
        });
    }

    /**
     * Валидация email при потере фокуса.
     */
    function _initEmailValidation() {
        var email = _elements.email;
        if (!email) return;

        email.addEventListener('blur', function () {
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

    /**
     * Обработка ввода адреса.
     */
    function _initAddressInput() {
        var address = _elements.address;
        if (!address) return;

        address.addEventListener('input', function () {
            var value = this.value.trim();
            var isDeliveryChecked = _elements.form
                ? _elements.form.querySelector('input[name="delivery_method"][value="delivery"]:checked')
                : null;

            if (value) {
                _updateDeliverySummary();
                if (isDeliveryChecked) {
                    _calculateDeliveryPrice();
                }
            }
        });
    }

    /**
     * Переключение radio-кнопок способа доставки.
     */
    function _initDeliveryToggle() {
        var radios = _elements.deliveryRadios;
        if (!radios || !radios.length) return;

        for (var i = 0; i < radios.length; i++) {
            radios[i].addEventListener('change', _updateAddressBlock);
        }
        _updateAddressBlock();
    }

    /**
     * Интеграция с виджетом Яндекс Доставки.
     */
    function _initYandexWidget() {
        var radios = _elements.deliveryRadios;
        if (!radios || !radios.length || !window.YandexDeliveryWidget) return;

        for (var i = 0; i < radios.length; i++) {
            var radio = radios[i];
            if (radio.value === 'delivery' && radio.checked) {
                setTimeout(function () {
                    window.YandexDeliveryWidget.openModal();
                }, CONFIG.YANDEX_WIDGET_OPEN_DELAY_MS);
            }

            (function (r) {
                r.addEventListener('change', function () {
                    if (this.checked && this.value === 'delivery') {
                        setTimeout(function () {
                            window.YandexDeliveryWidget.openModal();
                        }, CONFIG.YANDEX_WIDGET_OPEN_DELAY_MS);
                    }
                });
            })(radio);
        }
    }

    /**
     * Валидация полей имени и фамилии с debounce.
     */
    function _initNameFields() {
        var fields = [_elements.firstName, _elements.lastName];
        for (var i = 0; i < fields.length; i++) {
            var input = fields[i];
            if (!input) continue;

            input.addEventListener('input', CoffeeShop.debounce(function () {
                if (this.value.trim().length >= CONFIG.MIN_NAME_LENGTH) {
                    this.classList.remove('is-invalid');
                    this.classList.add('is-valid');
                }
            }, CONFIG.NAME_DEBOUNCE_MS));
        }
    }

    /**
     * Валидация формы перед отправкой.
     */
    function _initSubmitValidation() {
        var submitBtn = _elements.submitBtn;
        if (!submitBtn) return;

        submitBtn.addEventListener('click', function (e) {
            var isValid = true;
            var firstInvalid = null;

            // Проверка обязательных полей
            var requiredInputs = _elements.form.querySelectorAll('[required]');
            for (var i = 0; i < requiredInputs.length; i++) {
                var input = requiredInputs[i];
                if (!input.value.trim()) {
                    isValid = false;
                    input.classList.add('is-invalid');
                    if (!firstInvalid && input.classList.contains('form-control')) {
                        firstInvalid = input;
                    }
                } else {
                    input.classList.remove('is-invalid');
                    input.classList.add('is-valid');
                }
            }

            // Валидация email
            if (_elements.email && _elements.email.value && !isValidEmail(_elements.email.value)) {
                isValid = false;
                _elements.email.classList.add('is-invalid');
                if (!firstInvalid) firstInvalid = _elements.email;
            }

            // Валидация телефона
            if (_elements.phone) {
                var digits = _elements.phone.value.replace(/\D/g, '');
                if (digits.length < CONFIG.MIN_PHONE_DIGITS) {
                    isValid = false;
                    _elements.phone.classList.add('is-invalid');
                    if (!firstInvalid) firstInvalid = _elements.phone;
                }
            }

            if (!isValid) {
                e.preventDefault();
                if (firstInvalid) firstInvalid.focus();
                CoffeeShop.showToast('Заполните все обязательные поля', 'warning');
            }
        });
    }

    /**
     * Отображение итоговой суммы заказа.
     */
    function _initTotalDisplay() {
        var total = _elements.total;
        if (!total) return;

        var rawTotal = total.getAttribute('data-total');
        if (rawTotal) {
            total.textContent = CoffeeShop.formatPrice(rawTotal) + ' ₽';
        }
    }

    /* ==================== Основная инициализация ==================== */

    /**
     * Инициализация всех компонентов checkout-формы.
     */
    function init() {
        var form = document.querySelector('.checkout-form');
        if (!form) return;

        _cacheElements(form);

        _initPhoneFormatting();
        _initEmailValidation();
        _initAddressInput();
        _initDeliveryToggle();
        _initYandexWidget();
        _initNameFields();
        _initSubmitValidation();
        _initTotalDisplay();
    }

    /* ==================== Export ==================== */

    return {
        init: init,
        updateDeliverySummary: function (selectedType) {
            _cacheElements(document.querySelector('.checkout-form'));
            _updateDeliverySummary(selectedType);
        }
    };

})();

document.addEventListener('DOMContentLoaded', Checkout.init);
