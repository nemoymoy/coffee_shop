/**
 * Coffee Shop — Checkout (Refactored).
 *
 * Разделена ответственность:
 * - Checkout: валидация формы, управление блоком доставки
 * - YandexDeliveryWidget: полный контроль над UI доставки (сводка, цена, ETA)
 *
 * Больше нет дублирования — виджет сам обновляет delivery summary и order total.
 */
const Checkout = (() => {

    /* ==================== Config ==================== */
    const CONFIG = {
        NAME_DEBOUNCE_MS: 300,
        YANDEX_WIDGET_OPEN_DELAY_MS: 200,
        MIN_NAME_LENGTH: 2,
        MIN_PHONE_DIGITS: 11,
    };

    /* ==================== State ==================== */
    const state = {
        elements: {},
    };

    /* ==================== DOM ==================== */
    const $ = (s) => document.querySelector(s);
    const $$ = (s) => document.querySelectorAll(s);

    /* ==================== Cache ==================== */
    function cacheElements(form) {
        state.elements = {
            form,
            phone: form.querySelector('#id_phone'),
            email: form.querySelector('#id_email'),
            firstName: form.querySelector('#id_first_name'),
            lastName: form.querySelector('#id_last_name'),
            address: form.querySelector('#id_delivery_address'),
            addressBlock: form.querySelector('#addressBlock'),
            deliveryRadios: form.querySelectorAll('input[name="delivery_method"]'),
            deliveryInfo: form.querySelector('#deliveryInfo'),
            total: form.querySelector('#checkoutTotal'),
            submitBtn: form.querySelector('button[type="submit"]'),
        };
    }

    /* ==================== Phone ==================== */
    function initPhone() {
        const phone = state.elements.phone;
        if (!phone) return;
        phone.addEventListener('input', () => {
            const raw = phone.value.replace(/^(\+)?(?=8|7)/, '');
            if (typeof CoffeeShop !== 'undefined' && CoffeeShop.formatPhone) {
                phone.value = CoffeeShop.formatPhone(raw);
            }
        });
    }

    /* ==================== Email ==================== */
    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function initEmail() {
        const email = state.elements.email;
        if (!email) return;
        email.addEventListener('blur', () => {
            if (email.value && !isValidEmail(email.value)) {
                email.classList.add('is-invalid');
                email.nextElementSibling?.classList.contains('invalid-feedback') && (email.nextElementSibling.style.display = 'block');
            } else {
                email.classList.remove('is-invalid');
                email.classList.add('is-valid');
            }
        });
    }

    /* ==================== Name ==================== */
    function debounce(fn, delay) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), delay);
        };
    }

    function initNames() {
        const fields = [state.elements.firstName, state.elements.lastName];
        fields.forEach((input) => {
            if (!input) return;
            input.addEventListener('input', debounce(() => {
                if (input.value.trim().length >= CONFIG.MIN_NAME_LENGTH) {
                    input.classList.remove('is-invalid');
                    input.classList.add('is-valid');
                }
            }, CONFIG.NAME_DEBOUNCE_MS));
        });
    }

    /* ==================== Delivery Toggle ==================== */
    function initDeliveryToggle() {
        const radios = state.elements.deliveryRadios;
        if (!radios?.length) return;

        const isDeliveryChecked = () => $('input[name="delivery_method"][value="delivery"]:checked');
        const showAddress = () => {
            if (state.elements.addressBlock) state.elements.addressBlock.style.display = 'block';
            state.elements.address?.setAttribute('required', 'required');
        };
        const hideAddress = () => {
            if (state.elements.addressBlock) state.elements.addressBlock.style.display = 'none';
            state.elements.address?.removeAttribute('required');
            state.elements.address.value = '';
            if (state.elements.deliveryInfo) state.elements.deliveryInfo.style.display = 'none';
        };

        radios.forEach((radio) => {
            radio.addEventListener('change', () => {
                radio.checked ? showAddress() : hideAddress();
            });
        });

        isDeliveryChecked() ? showAddress() : hideAddress();
    }

    /* ==================== Yandex Widget ==================== */
    function initYandexWidget() {
        const radios = state.elements.deliveryRadios;
        if (!radios?.length) return;
        radios.forEach((radio) => {
            radio.addEventListener('change', () => {
                if (radio.checked && radio.value === 'delivery') {
                    setTimeout(() => {
                        if (typeof YandexDeliveryWidget !== 'undefined' && YandexDeliveryWidget.openModal) {
                            YandexDeliveryWidget.openModal();
                        }
                    }, CONFIG.YANDEX_WIDGET_OPEN_DELAY_MS);
                }
            });
        });
    }

    /* ==================== Total Display ==================== */
    function initTotal() {
        const totalEl = state.elements.total;
        if (!totalEl) return;
        const raw = totalEl.textContent.replace(/[^0-9.,]/g, '').replace(',', '.').trim();
        if (raw) {
            if (typeof CoffeeShop !== 'undefined' && CoffeeShop.formatPrice) {
                totalEl.textContent = CoffeeShop.formatPrice(raw);
            } else {
                totalEl.textContent = parseFloat(raw).toLocaleString('ru-RU');
            }
        }
    }

    /* ==================== Toast ==================== */
    function showToast(message, type = 'info') {
        if (typeof CoffeeShop !== 'undefined' && CoffeeShop.showToast) {
            CoffeeShop.showToast(message, type);
        }
    }

    /* ==================== Submit Validation ==================== */
    function initSubmit() {
        const btn = state.elements.submitBtn;
        if (!btn) return;

        btn.addEventListener('click', (e) => {
            let valid = true;
            let first = null;

            // Required fields
            state.elements.form.querySelectorAll('[required]').forEach((input) => {
                if (!input.value.trim()) {
                    valid = false;
                    input.classList.add('is-invalid');
                    if (!first && input.classList.contains('form-control')) first = input;
                } else {
                    input.classList.remove('is-invalid');
                    input.classList.add('is-valid');
                }
            });

            // Email
            if (state.elements.email?.value && !isValidEmail(state.elements.email.value)) {
                valid = false;
                state.elements.email.classList.add('is-invalid');
                if (!first) first = state.elements.email;
            }

            // Phone
            if (state.elements.phone) {
                const digits = state.elements.phone.value.replace(/\D/g, '');
                if (digits.length < CONFIG.MIN_PHONE_DIGITS) {
                    valid = false;
                    state.elements.phone.classList.add('is-invalid');
                    if (!first) first = state.elements.phone;
                }
            }

            // Delivery address
            if ($('input[name="delivery_method"][value="delivery"]:checked')) {
                if (!state.elements.address?.value.trim()) {
                    valid = false;
                    if (!first) first = state.elements.address;
                    showToast('Пожалуйста, выберите адрес доставки', 'warning');
                    return;
                }
            }

            if (!valid) {
                e.preventDefault();
                if (first) first.focus();
                showToast('Заполните все обязательные поля', 'warning');
            }
        });
    }

    /* ==================== Init ==================== */
    function init() {
        const form = $('.checkout-form');
        if (!form) return;
        cacheElements(form);
        initPhone();
        initEmail();
        initNames();
        initDeliveryToggle();
        initYandexWidget();
        initSubmit();
        initTotal();
    }

    return { init };

})();

document.addEventListener('DOMContentLoaded', Checkout.init);
