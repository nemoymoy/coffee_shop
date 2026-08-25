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
        _elements.deliveryInfo = document.getElementById('deliveryInfo');
        _elements.selectedDeliveryType = document.getElementById('selectedDeliveryType');
        _elements.selectedDeliveryAddress = document.getElementById('selectedDeliveryAddress');
        _elements.selectedDeliveryCost = document.getElementById('selectedDeliveryCost');
        _elements.selectedDeliveryEta = document.getElementById('selectedDeliveryEta');
        _elements.addressBlock = document.getElementById('addressBlock');
        _elements.total = document.getElementById('checkoutTotal');
        _elements.orderGoodsTotal = document.getElementById('orderGoodsTotal');
        _elements.orderDeliveryCost = document.getElementById('orderDeliveryCost');
        _elements.yandexDeliveryTypeInput = document.getElementById('id_yandex_delivery_type');
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
                    // Ошибка — показываем ошибку, не маскируем
                    _setDeliveryError(data.error || 'Не удалось рассчитать стоимость доставки');
                }
            })
            .catch(function () {
                _setDeliveryError('Ошибка подключения к сервису расчёта доставки');
            });
        }, CONFIG.DELIVERY_CALCULATION_DEBOUNCE_MS);
    }

    /**
     * Обновление сводки доставки.
     */
    function _updateDeliverySummary(selectedTypeOverride) {
        var addressValue = _elements.address ? _elements.address.value.trim() : '';
        var isDeliveryChecked = _elements.form
            ? _elements.form.querySelector('input[name="delivery_method"][value="delivery"]:checked')
            : null;

        if (!addressValue || !isDeliveryChecked) {
            if (_elements.deliveryInfo) {
                _elements.deliveryInfo.style.display = 'none';
            }
            return;
        }

        var selectedType = selectedTypeOverride || null;
        if (!selectedType && window.YandexDeliveryWidget && window.YandexDeliveryWidget.getSelectedType) {
            selectedType = window.YandexDeliveryWidget.getSelectedType();
        }

        var typeLabel = CONFIG.DELIVERY_SUMMARY_TYPES[selectedType || 'courier'] || CONFIG.DELIVERY_SUMMARY_TYPES.courier;
        var priceText = _elements.selectedDeliveryCost ? _elements.selectedDeliveryCost.textContent : '—';
        var etaText = _elements.selectedDeliveryEta ? _elements.selectedDeliveryEta.textContent : '';

        var price = parseFloat(priceText.replace(/[^0-9.,]/g, '').replace(',', '.'));
        if (!price || price <= 0) {
            // Если цена не задана или это ошибка — не показываем сводку
            return;
        }

        _showDeliveryInfo(typeLabel, addressValue, price, etaText, selectedType || '');
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
        if (_elements.deliveryInfo) {
            _elements.deliveryInfo.style.display = 'none';
        }
        _setDeliveryPlaceholder();
    }

    function _showDeliveryInfo(typeLabel, address, price, eta, yandexType) {
        if (!_elements.deliveryInfo) return;

        if (_elements.selectedDeliveryType) {
            _elements.selectedDeliveryType.textContent = typeLabel;
        }
        if (_elements.selectedDeliveryAddress) {
            _elements.selectedDeliveryAddress.textContent = address;
        }
        if (_elements.selectedDeliveryCost) {
            _elements.selectedDeliveryCost.textContent = CoffeeShop.formatPrice(price) + ' ₽';
        }
        if (_elements.selectedDeliveryEta) {
            _elements.selectedDeliveryEta.textContent = eta || '';
        }

        // Записываем тип Яндекс Доставки в скрытое поле формы
        if (_elements.yandexDeliveryTypeInput && yandexType) {
            _elements.yandexDeliveryTypeInput.value = yandexType;
        }

        _elements.deliveryInfo.style.display = 'block';
    }

    function _setDeliveryPlaceholder() {
        if (_elements.selectedDeliveryCost) _elements.selectedDeliveryCost.textContent = '—';
        if (_elements.orderDeliveryCost) _elements.orderDeliveryCost.textContent = '—';
    }

    function _setDeliveryLoading() {
        if (_elements.selectedDeliveryCost) _elements.selectedDeliveryCost.textContent = 'Расчёт...';
    }

    function _setDeliveryResult(price, eta) {
        if (_elements.selectedDeliveryCost) {
            _elements.selectedDeliveryCost.textContent = CoffeeShop.formatPrice(price) + ' ₽';
        }
        if (_elements.orderDeliveryCost) {
            _elements.orderDeliveryCost.textContent = CoffeeShop.formatPrice(price) + ' ₽';
        }
        if (_elements.selectedDeliveryEta) {
            _elements.selectedDeliveryEta.textContent = eta || '';
        }
        _updateOrderTotal(price);
        _updateDeliverySummary();
    }

    function _setDeliveryError(message) {
        if (_elements.selectedDeliveryCost) {
            _elements.selectedDeliveryCost.textContent = 'Ошибка: ' + message;
            _elements.selectedDeliveryCost.style.color = 'red';
        }
        if (_elements.orderDeliveryCost) {
            _elements.orderDeliveryCost.textContent = '—';
        }
        if (_elements.selectedDeliveryEta) {
            _elements.selectedDeliveryEta.textContent = '';
        }
        _updateDeliverySummary();
        if (typeof CoffeeShop !== 'undefined' && CoffeeShop.showToast) {
            CoffeeShop.showToast(message, 'danger');
        }
    }

    /**
     * Обновление итоговой суммы заказа (товары + доставка).
     */
    function _updateOrderTotal(deliveryPrice) {
        var goodsTotalText = _elements.orderGoodsTotal ? _elements.orderGoodsTotal.textContent.trim() : '0';
        var goodsTotal = parseFloat(goodsTotalText.replace(/[^0-9.,]/g, '').replace(',', '.')) || 0;
        var newTotal = goodsTotal + deliveryPrice;

        if (_elements.total) {
            _elements.total.textContent = CoffeeShop.formatPrice(newTotal);
        }
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

            // Валидация адреса доставки
            var isDeliveryChecked = _elements.form
                ? _elements.form.querySelector('input[name="delivery_method"][value="delivery"]:checked')
                : null;
            if (isDeliveryChecked && _elements.address) {
                var addressValue = _elements.address.value.trim();
                if (!addressValue) {
                    isValid = false;
                    if (!firstInvalid) firstInvalid = _elements.address;
                    CoffeeShop.showToast('Пожалуйста, выберите адрес доставки', 'warning');
                    return;
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
     * Инициализация итоговой суммы заказа.
     */
    function _initTotalDisplay() {
        var total = _elements.total;
        if (!total) return;

        // Получаем начальную сумму из текста, убираем символ ₽ если есть
        var rawTotal = total.textContent.replace(/[^0-9.,]/g, '').replace(',', '.').trim();
        if (rawTotal) {
            total.textContent = CoffeeShop.formatPrice(rawTotal);
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
        },
        updateOrderTotal: function (deliveryPrice) {
            _cacheElements(document.querySelector('.checkout-form'));
            _updateOrderTotal(deliveryPrice);
        }
    };

})();

document.addEventListener('DOMContentLoaded', Checkout.init);
