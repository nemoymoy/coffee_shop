/**
 * Coffee Shop — общие утилиты.
 */
var CoffeeShop = window.CoffeeShop || {};

(function () {

    /* ======================= AJAX helpers ======================= */

    /**
     * Выполнить CSRF-safe POST запрос.
     */
    CoffeeShop.postJson = function (url, data) {
        var csrftoken = getCookie('csrftoken');
        return fetch(url, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: encodeFormData(data)
        }).then(function (resp) {
            return resp.text().then(function (text) {
                var json;
                try {
                    json = JSON.parse(text);
                } catch (e) {
                    if (!resp.ok) {
                        return Promise.reject({
                            error: 'Серверная ошибка',
                            redirect: '/accounts/login/'
                        });
                    }
                    return JSON.parse('{}');
                }
                if (!resp.ok) {
                    return Promise.reject(json);
                }
                return json;
            });
        });
    };

    /**
     * Выполнить GET запрос.
     */
    CoffeeShop.getJson = function (url) {
        return fetch(url).then(function (resp) {
            return resp.json().then(function (json) {
                if (!resp.ok) {
                    return Promise.reject(json);
                }
                return json;
            });
        });
    };

    /* ======================= Cookie helper ======================= */

    function getCookie(name) {
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
        return cookieValue;
    }

    /* ======================= Formatters ======================= */

    /**
     * Отформатировать число как цену (русский формат).
     */
    CoffeeShop.formatPrice = function (value) {
        var num = parseFloat(value);
        if (isNaN(num)) return '0,00';
        return num.toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    };

    /**
     * Отформатировать телефон в +7 (XXX) XXX-XX-XX.
     */
    CoffeeShop.formatPhone = function (raw) {
        var digits = raw.replace(/\D/g, '');
        if (digits.length === 0) return '';
        if (digits[0] === '8' && digits.length === 11) {
            digits = '7' + digits.substring(1);
        }
        if (digits[0] !== '7') digits = '7' + digits;
        if (digits.length < 11) return raw;
        return '+' + digits.substring(0, 1) +
            ' (' + digits.substring(1, 4) + ') ' +
            digits.substring(4, 7) + '-' +
            digits.substring(7, 9) + '-' +
            digits.substring(9, 11);
    };

    /* ======================= Utilities ======================= */

    /**
     * Получить cookie по имени.
     */
    CoffeeShop.getCookie = function (name) {
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
        return cookieValue;
    };

    /**
     * Парсить адресную строку в структурированные данные.
     * Формат: "Город, улица, дом-кв"
     */
    CoffeeShop.parseAddress = function (raw) {
        var result = {
            city: '',
            street: '',
            house: '',
            apartment: ''
        };
        var parts = raw.split(',').map(function (s) { return s.trim(); });

        if (parts.length >= 1) result.city = parts[0];
        if (parts.length >= 2) result.street = parts[1];
        if (parts.length >= 3) {
            var houseParts = parts[2].split('-');
            result.house = houseParts[0].trim();
            if (houseParts.length > 1) {
                result.apartment = houseParts[1].trim();
            }
        }

        return result;
    };

    /**
     * Debounce — задержка вызова функции.
     */
    CoffeeShop.debounce = function (func, wait) {
        var timeout;
        return function () {
            var context = this;
            var args = arguments;
            clearTimeout(timeout);
            timeout = setTimeout(function () {
                func.apply(context, args);
            }, wait);
        };
    };

    /**
     * Показать toast уведомление.
     */
    CoffeeShop.showToast = function (message, type) {
        type = type || 'info';
        var container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.style.cssText = 'position: fixed; top: 80px; right: 20px; z-index: 9999;';
            document.body.appendChild(container);
        }
        var bgClass = {
            success: 'bg-success',
            danger: 'bg-danger',
            warning: 'bg-warning text-dark',
            info: 'bg-info text-dark'
        }[type] || 'bg-info';

        var toastEl = document.createElement('div');
        toastEl.className = 'toast ' + bgClass + ' text-white';
        toastEl.setAttribute('role', 'alert');
        toastEl.setAttribute('aria-live', 'assertive');
        toastEl.setAttribute('aria-atomic', 'true');
        toastEl.innerHTML = '<div class="toast-body">' + message + '</div>';
        container.appendChild(toastEl);

        var bsToast = new bootstrap.Toast(toastEl, { delay: 3000 });
        bsToast.show();
        toastEl.addEventListener('hidden.bs.toast', function () {
            toastEl.remove();
        });
    };

    /**
     * Кодировка formData.
     */
    function encodeFormData(data) {
        var params = [];
        for (var key in data) {
            if (Object.prototype.hasOwnProperty.call(data, key)) {
                params.push(encodeURIComponent(key) + '=' + encodeURIComponent(data[key]));
            }
        }
        return params.join('&');
    }

    /* ======================= DOM Ready ======================= */

    document.addEventListener('DOMContentLoaded', function () {
        var alertEl = document.querySelector('.alert-dismissible');
        if (alertEl) {
            CoffeeShop.showToast(alertEl.textContent.trim(), 'info');
        }
    });

})();
