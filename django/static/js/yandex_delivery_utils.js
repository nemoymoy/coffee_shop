/**
 * Coffee Shop — Yandex Delivery Utility Functions.
 *
 * Общие утилиты для всех модулей Яндекс Доставки:
 * - CSRF токен
 * - Форматирование цен
 * - DOM helpers
 * - Fetch-обёртки
 */
var YandexDeliveryUtils = (function () {
    'use strict';

    /* ==================== CSRF ==================== */

    function getCsrfToken() {
        var tokenInput = document.querySelector('[name=csrftokenmiddlewaretoken]');
        if (tokenInput) {
            return tokenInput.value;
        }
        return _extractCsrfFromCookie();
    }

    function _extractCsrfFromCookie() {
        var cookieName = 'csrftoken';
        if (!document.cookie || document.cookie === '') {
            return '';
        }

        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, cookieName.length + 1) === (cookieName + '=')) {
                return decodeURIComponent(cookie.substring(cookieName.length + 1));
            }
        }
        return '';
    }

    function buildFetchOptions(body) {
        return {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify(body)
        };
    }

    /* ==================== Price Formatting ==================== */

    function formatPrice(price) {
        return parseFloat(price).toLocaleString('ru-RU', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });
    }

    /* ==================== DOM Helpers ==================== */

    function $(selector) {
        return document.querySelector(selector);
    }

    function $$(selector) {
        return document.querySelectorAll(selector);
    }

    function showElement(el) {
        if (el) el.style.display = 'block';
    }

    function hideElement(el) {
        if (el) el.style.display = 'none';
    }

    function setFieldvalue(fieldId, value) {
        var field = $(fieldId);
        if (field) {
            field.value = value;
        }
    }

    function setTextContent(el, text) {
        if (el) {
            el.textContent = text;
        }
    }

    /* ==================== Error Display ==================== */

    function showInlineError(containerId, message) {
        var container = $(containerId);
        if (!container) return;

        // Проверяем, является ли контейнер block с ценой (courierPriceBlock)
        if (container.id === 'courierPriceBlock') {
            container.innerHTML = '❌ ' + _escapeHtml(message);
            container.style.background = '#ffebee';
            container.style.color = '#c62828';
        } else {
            // Для обычного cost элемента
            container.textContent = '❌ ' + message;
            container.style.color = 'red';
        }
    }

    function showInlineSuccess(containerId, message) {
        var container = $(containerId);
        if (!container) return;

        if (container.id === 'courierPriceBlock') {
            container.innerHTML = '✅ ' + _escapeHtml(message);
            container.style.background = '';
            container.style.color = '';
        }
    }

    function _escapeHtml(text) {
        if (!text) return '';
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    /* ==================== Loading States ==================== */

    function showLoading(costEl) {
        if (costEl) {
            costEl.textContent = 'Расчёт...';
            costEl.style.color = '';
        }
    }

    function showEtaText(days) {
        return days ? ('  • ' + days + ' дн.') : '';
    }

    /* ==================== Public API ==================== */

    return {
        getCsrfToken: getCsrfToken,
        buildFetchOptions: buildFetchOptions,
        formatPrice: formatPrice,
        $: $,
        $$: $$,
        showElement: showElement,
        hideElement: hideElement,
        setFieldValue: setFieldvalue,
        setTextContent: setTextContent,
        showInlineError: showInlineError,
        showInlineSuccess: showInlineSuccess,
        showLoading: showLoading,
        showEtaText: showEtaText,
        escapeHtml: _escapeHtml
    };
})();
