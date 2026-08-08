/**
 * Coffee Shop — Checkout.
 * Валидация формы оформления заказа, переключение способа получения,
 * debounced-обработка полей.
 */
var Checkout = (function () {

    /* ==================== Инициализация ==================== */

    function init() {
        var form = document.querySelector('.checkout-form');
        if (!form) return;

        var phoneInput = form.querySelector('#id_phone');
        var emailInput = form.querySelector('#id_email');
        var firstNameInput = form.querySelector('#id_first_name');
        var lastNameInput = form.querySelector('#id_last_name');
        var addressInput = form.querySelector('#id_delivery_address');
        var deliveryMethod = form.querySelector('input[name="delivery_method"]');
        var addressBlock = document.getElementById('addressBlock');
        var submitBtn = form.querySelector('button[type="submit"]');
        var totalEl = document.getElementById('checkoutTotal');

        /* ---- Phone formatting ---- */
        if (phoneInput) {
            phoneInput.addEventListener('input', function () {
                var raw = this.value.replace(/^(\+)?(?=8|7)/, '');
                var formatted = CoffeeShop.formatPhone(raw);
                this.value = formatted;
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

        /* ---- Delivery method toggle ---- */
        if (deliveryMethod && addressBlock) {
            var updateAddressBlock = debounce(function () {
                var checked = form.querySelector('input[name="delivery_method"][value="delivery"]');
                if (checked && checked.checked) {
                    addressBlock.style.display = 'block';
                    addressInput.setAttribute('required', 'required');
                } else {
                    addressBlock.style.display = 'none';
                    addressInput.removeAttribute('required');
                    addressInput.value = '';
                }
            }, 150);

            form.querySelectorAll('input[name="delivery_method"]').forEach(function (radio) {
                radio.addEventListener('change', updateAddressBlock);
            });

            // Инициализация
            updateAddressBlock();
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

    /* ==================== Helpers ==================== */

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

    /* ==================== Export ==================== */

    return {
        init: init
    };

})();

document.addEventListener('DOMContentLoaded', Checkout.init);
