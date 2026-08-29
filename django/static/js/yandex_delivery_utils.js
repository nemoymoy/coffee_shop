/**
 * Coffee Shop — Yandex Delivery Utility Functions.
 *
 * Общие утилиты для всех модулей Яндекс Доставки:
 * - CSRF токен
 * - Форматирование цен
 * - DOM helpers
 */
const YandexDeliveryUtils = (() => {

    /* ==================== CSRF ==================== */

    /**
     * Получает CSRF токен из формы или cookie.
     * @returns {string}
     */
    function getCsrfToken() {
        const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenInput) return tokenInput.value;
        return _extractCsrfFromCookie();
    }

    /**
     * Извлекает CSRF токен из cookie.
     * @returns {string}
     */
    function _extractCsrfFromCookie() {
        const cookieName = 'csrftoken';
        if (!document.cookie) return '';
        return document.cookie
            .split(';')
            .map(c => c.trim())
            .find(c => c.startsWith(`${cookieName}=`))
            ?.substring(cookieName.length + 1);
    }

    /* ==================== Price Formatting ==================== */

    /**
     * Форматирует цену в рублях по российскому стандарту.
     * @param {number|string} price
     * @returns {string}
     */
    function formatPrice(price) {
        return parseFloat(price).toLocaleString('ru-RU', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });
    }

    /* ==================== DOM Helpers ==================== */

    /**
     * Находит элемент по CSS-селектору.
     * @param {string} selector
     * @returns {Element|null}
     */
    function $(selector) {
        return document.querySelector(selector);
    }

    /**
     * Находит все элементы по CSS-селектору.
     * @param {string} selector
     * @returns {NodeListOf<Element>}
     */
    function $$(selector) {
        return document.querySelectorAll(selector);
    }

    /**
     * Показывает элемент (убирает класс d-none).
     * @param {Element|null} el
     */
    function showElement(el) {
        el?.classList.remove('d-none');
    }

    /**
     * Скрывает элемент (добавляет класс d-none).
     * @param {Element|null} el
     */
    function hideElement(el) {
        el?.classList.add('d-none');
    }

    /**
     * Устанавливает value поля формы.
     * @param {string} fieldId
     * @param {string} value
     */
    function setFieldValue(fieldId, value) {
        const field = $(fieldId);
        if (field) field.value = value;
    }

    /**
     * Устанавливает textContent элемента.
     * @param {Element|null} el
     * @param {string} text
     */
    function setTextContent(el, text) {
        if (el) el.textContent = text;
    }

    /**
     * Устанавливает innerHTML элемента с экранированием HTML.
     * @param {Element|null} el
     * @param {string} html
     */
    function setHtmlContent(el, html) {
        if (el) el.innerHTML = _escapeHtml(html);
    }

    /* ==================== Error Display ==================== */

    /**
     * Показывает сообщение об ошибке в блоке цены (для курьера).
     * @param {Element|null} container
     * @param {string} message
     */
    function showPriceError(container, message) {
        if (!container) return;
        container.innerHTML = `<span class="text-danger">❌ ${_escapeHtml(message)}</span>`;
        container.classList.add('border-danger');
    }

    /**
     * Показывает успешное сообщение в блоке цены.
     * @param {Element|null} container
     * @param {string} message
     */
    function showPriceSuccess(container, message) {
        if (!container) return;
        container.innerHTML = `<span class="text-success">✅ ${_escapeHtml(message)}</span>`;
        container.classList.remove('border-danger');
    }

    /* ==================== Loading States ==================== */

    /**
     * Устанавливает состояние загрузки в элемент цены.
     * @param {Element|null} costEl
     */
    function showLoading(costEl) {
        if (costEl) {
            costEl.textContent = 'Расчёт...';
            costEl.classList.remove('text-danger', 'text-success');
        }
    }

    /**
     * Формирует текст ETA (estimated time of arrival).
     * @param {number|null} days
     * @returns {string}
     */
    function showEtaText(days) {
        return days ? ` • ${days} дн.` : '';
    }

    /* ==================== HTML Escaping ==================== */

    /**
     * Экранирует HTML-сущности.
     * @param {string} text
     * @returns {string}
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    /* ==================== Public API ==================== */

    return {
        getCsrfToken,
        formatPrice,
        $,
        $$,
        showElement,
        hideElement,
        setFieldValue,
        setTextContent,
        setHtmlContent,
        showPriceError,
        showPriceSuccess,
        showLoading,
        showEtaText,
        escapeHtml
    };

})();
