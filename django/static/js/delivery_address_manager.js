/**
 * Coffee Shop — Delivery Address Management (Profile Page).
 *
 * Управление сохранёнными адресами доставки на странице профиля:
 * - Добавление адреса с автокомплитом Яндекс
 * - Редактирование адреса
 * - Удаление адреса
 * - Установка адреса по умолчанию
 */
const DeliveryAddressManager = (() => {

    /* ==================== State ==================== */
    const state = {
        addresses: [],
        debounceTimer: null,
        autocompleteIndex: -1,
        suggestions: [],
        deleteTargetId: null,
        GEOCODE_URL: '/checkout/geocode-address/',
        API_ADDRESSES_URL: '/accounts/api/addresses/',
    };

    /* ==================== JSON Response Parser ==================== */
    async function parseJsonResponse(response) {
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            const text = await response.text();
            console.error('[DeliveryAddress] Expected JSON but got:', contentType, text.substring(0, 200));
            return {
                success: false,
                error: `Сервер вернул ${response.status}. Проверьте консоль разработчика.`,
            };
        }
        try {
            return await response.json();
        } catch (e) {
            console.error('[DeliveryAddress] JSON parse error:', e);
            return {
                success: false,
                error: 'Ошибка парсинга ответа сервера',
            };
        }
    }

    /* ==================== CSRF Token ==================== */
    function getCsrfToken() {
        const name = 'csrftoken';
        let cookieValue;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
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

    function setFieldValue(id, value) {
        const el = $(`#${id}`);
        if (el) el.value = value || '';
    }

    function getFieldValue(id) {
        const el = $(`#${id}`);
        return el ? el.value.trim() : '';
    }

    /* ==================== Autocomplete ==================== */
    function initAutocomplete() {
        const input = $('#addressAutocompleteInput');
        if (!input) return;

        input.addEventListener('input', function () {
            const query = this.value.trim();
            clearTimeout(state.debounceTimer);

            if (query.length < 3) {
                hideSuggestions();
                return;
            }

            state.debounceTimer = setTimeout(() => {
                fetchSuggestions(query);
            }, 600);
        });

        input.addEventListener('keydown', function (e) {
            if (state.suggestions.length === 0) return;

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                state.autocompleteIndex = Math.min(
                    state.autocompleteIndex + 1,
                    state.suggestions.length - 1
                );
                updateSuggestionsUI();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                state.autocompleteIndex = Math.max(
                    state.autocompleteIndex - 1,
                    -1
                );
                updateSuggestionsUI();
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (state.autocompleteIndex >= 0 && state.autocompleteIndex < state.suggestions.length) {
                    selectSuggestion(state.autocompleteIndex);
                }
            } else if (e.key === 'Escape') {
                hideSuggestions();
                state.autocompleteIndex = -1;
            }
        });
    }

    async function fetchSuggestions(query) {
        try {
            const response = await fetch(state.GEOCODE_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ query: query }),
            });

            const data = await response.json();

            if (data.success && data.features && data.features.length > 0) {
                state.suggestions = data.features;
                state.autocompleteIndex = -1;
                showSuggestions(data.features);
            } else {
                hideSuggestions();
            }
        } catch (error) {
            console.error('[DeliveryAddress] Autocomplete error:', error);
            hideSuggestions();
        }
    }

    function showSuggestions(features) {
        const container = $('#addressSuggestions');
        if (!container) return;

        container.innerHTML = '';
        features.forEach((feature, index) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'list-group-item list-group-item-action';
            btn.textContent = feature.text;
            btn.addEventListener('click', () => selectSuggestion(index));
            container.appendChild(btn);
        });

        showElement(container);
    }

    function hideSuggestions() {
        const container = $('#addressSuggestions');
        hideElement(container);
    }

    function updateSuggestionsUI() {
        const items = $$('#addressSuggestions .list-group-item');
        items.forEach((item, index) => {
            item.classList.toggle('active', index === state.autocompleteIndex);
        });
    }

    function selectSuggestion(index) {
        if (index < 0 || index >= state.suggestions.length) return;

        const suggestion = state.suggestions[index];
        setFieldValue('addressAutocompleteInput', suggestion.text);
        setFieldValue('addressFullAddress', suggestion.text);

        // Сохраняем координаты в data-атрибут формы
        const fullAddressField = $('#addressFullAddress');
        if (suggestion.coords) {
            fullAddressField.dataset.coords = `${suggestion.coords[0]},${suggestion.coords[1]}`;
        }

        hideSuggestions();
        state.autocompleteIndex = -1;

        // Закрываем модалку автокомплита при клике вне
        document.addEventListener('click', function closeSuggestion(e) {
            const input = $('#addressAutocompleteInput');
            const container = $('#addressSuggestions');
            if (!input.contains(e.target) && !container.contains(e.target)) {
                hideSuggestions();
                document.removeEventListener('click', closeSuggestion);
            }
        });
    }

    /* ==================== Modal Management ==================== */
    function initModals() {
        const addressModal = new bootstrap.Modal($('#addressModal'));
        const deleteModal = new bootstrap.Modal($('#deleteAddressModal'));

        // Open add modal
        const addBtn = $('#addAddressBtn');
        const addBtnEmpty = $('#addAddressBtnEmpty');

        function openAddModal() {
            $('#addressModalTitle').textContent = 'Новый адрес';
            $('#addressEditId').value = '';
            $('#addressForm').reset();
            const isDefaultCheck = $('#addressIsDefault');
            if (isDefaultCheck) isDefaultCheck.checked = false;
            hideSuggestions();
            addressModal.show();
        }

        if (addBtn) addBtn.addEventListener('click', openAddModal);
        if (addBtnEmpty) addBtnEmpty.addEventListener('click', openAddModal);

        // Save address
        $('#saveAddressBtn').addEventListener('click', saveAddress);

        // Edit address
        $$('.btn-edit-address').forEach(btn => {
            btn.addEventListener('click', () => openEditModal(btn.dataset.addressId));
        });

        // Delete address
        $$('.btn-delete-address').forEach(btn => {
            btn.addEventListener('click', () => openDeleteModal(btn.dataset.addressId));
        });

        // Confirm delete
        $('#confirmDeleteBtn').addEventListener('click', deleteAddress);
    }

    async function openEditModal(addressId) {
        try {
            const response = await fetch(`${state.API_ADDRESSES_URL}${addressId}/`, {
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                },
            });

            const data = await parseJsonResponse(response);
            if (!data.success || !data.address) return;

            const address = data.address;
            const modal = new bootstrap.Modal($('#addressModal'));
            $('#addressModalTitle').textContent = 'Редактировать адрес';
            $('#addressEditId').value = address.id;
            setFieldValue('addressLabel', address.label);
            setFieldValue('addressAutocompleteInput', address.full_address);
            setFieldValue('addressFullAddress', address.full_address);
            $('#addressFullAddress').dataset.coords = address.coordinates || '';
            setFieldValue('addressApartment', address.apartment);
            const isDefaultCheck = $('#addressIsDefault');
            if (isDefaultCheck) isDefaultCheck.checked = address.is_default;

            modal.show();
        } catch (error) {
            console.error('[DeliveryAddress] Load address error:', error);
            showNotification('Не удалось загрузить адрес', 'danger');
        }
    }

    function openDeleteModal(addressId) {
        state.deleteTargetId = addressId;
        const address = state.addresses.find(a => a.id == addressId);
        const text = address
            ? `Вы действительно хотите удалить адрес "${address.label}" (${address.full_address})?`
            : 'Вы действительно хотите удалить этот адрес?';
        $('#deleteAddressText').textContent = text;
        new bootstrap.Modal($('#deleteAddressModal')).show();
    }

    /* ==================== Load Addresses ==================== */
    async function loadAddressesList() {
        try {
            const response = await fetch(state.API_ADDRESSES_URL, {
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                },
            });

            const data = await parseJsonResponse(response);
            if (data.success) {
                state.addresses = data.addresses || [];
                renderAddresses();
            }
        } catch (error) {
            console.error('[DeliveryAddress] Load addresses error:', error);
        }
    }

    /* ==================== CRUD Operations ==================== */
    async function saveAddress() {
        const editId = $('#addressEditId').value;
        const label = getFieldValue('addressLabel');
        const fullAddress = getFieldValue('addressFullAddress');
        const coordinates = $('#addressFullAddress')?.dataset?.coords || '';
        const apartment = getFieldValue('addressApartment');
        const isDefault = $('#addressIsDefault')?.checked || false;

        // Validation
        if (!label) {
            showNotification('Укажите метку адреса', 'warning');
            return;
        }
        if (!fullAddress) {
            showNotification('Выберите адрес из подсказок', 'warning');
            return;
        }

        const saveBtn = $('#saveAddressBtn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Сохранение...';

        try {
            let data;
            let response;

            if (editId) {
                // Update existing address
                response = await fetch(`${state.API_ADDRESSES_URL}${editId}/`, {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: JSON.stringify({
                        label: label,
                        apartment: apartment,
                        is_default: isDefault,
                    }),
                });

                data = await parseJsonResponse(response);
            } else {
                // Create new address
                response = await fetch(state.API_ADDRESSES_URL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrfToken(),
                    },
                    body: JSON.stringify({
                        label: label,
                        full_address: fullAddress,
                        coordinates: coordinates,
                        apartment: apartment,
                        is_default: isDefault,
                    }),
                });

                data = await parseJsonResponse(response);
            }

            if (data.success) {
                // Перезагружаем список адресов с сервера
                // (сервер мог изменить is_default у других адресов)
                await loadAddressesList();

                if (editId) {
                    showNotification('Адрес обновлён', 'success');
                } else {
                    showNotification('Адрес добавлен', 'success');
                }

                // Close modal
                bootstrap.Modal.getInstance($('#addressModal')).hide();
            } else {
                showNotification(data.error || 'Ошибка при сохранении', 'danger');
            }
        } catch (error) {
            console.error('[DeliveryAddress] Save error:', error);
            showNotification('Ошибка при сохранении адреса', 'danger');
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Сохранить';
        }
    }

    async function deleteAddress() {
        if (!state.deleteTargetId) return;

        const confirmBtn = $('#confirmDeleteBtn');
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Удаление...';

        try {
            const response = await fetch(
                `${state.API_ADDRESSES_URL}${state.deleteTargetId}/delete/`,
                {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                    },
                }
            );

            const data = await parseJsonResponse(response);
            if (data.success) {
                await loadAddressesList();
                showNotification('Адрес удалён', 'success');
                bootstrap.Modal.getInstance($('#deleteAddressModal')).hide();
            } else {
                showNotification(data.error || 'Ошибка при удалении', 'danger');
            }
        } catch (error) {
            console.error('[DeliveryAddress] Delete error:', error);
            showNotification('Ошибка при удалении адреса', 'danger');
        } finally {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Удалить';
        }
    }

    /* ==================== Render ==================== */
    function renderAddresses() {
        const container = $('#addressesList');
        if (!container) return;

        if (state.addresses.length === 0) {
            container.innerHTML = `
                <div class="text-center py-4">
                    <p class="text-muted">У вас пока нет сохранённых адресов</p>
                    <button class="btn btn-coffee-outline btn-sm" id="addAddressBtnEmpty">
                        Добавить адрес
                    </button>
                </div>
            `;
            const emptyBtn = container.querySelector('#addAddressBtnEmpty');
            if (emptyBtn) {
                emptyBtn.addEventListener('click', () => {
                    const modal = new bootstrap.Modal($('#addressModal'));
                    $('#addressModalTitle').textContent = 'Новый адрес';
                    $('#addressEditId').value = '';
                    $('#addressForm').reset();
                    hideSuggestions();
                    modal.show();
                });
            }
            return;
        }

        container.innerHTML = '';
        state.addresses.forEach(addr => {
            const card = document.createElement('div');
            card.className = `card mb-2 border-start border-4 ${addr.is_default ? 'border-primary' : 'border-secondary'}`;
            card.dataset.addressId = addr.id;

            card.innerHTML = `
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <div class="d-flex align-items-center gap-2">
                                <strong>${escapeHtml(addr.label || 'Дом')}</strong>
                                ${addr.is_default ? '<span class="badge bg-primary" title="Адрес по умолчанию">⭐ По умолчанию</span>' : ''}
                            </div>
                            <p class="mb-1 mt-2 small">${escapeHtml(addr.address || addr.full_address)}</p>
                            ${addr.apartment ? `<small class="text-muted">Кв. ${escapeHtml(addr.apartment)}</small>` : ''}
                        </div>
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-primary me-1 btn-edit-address" data-address-id="${addr.id}" title="Редактировать">✏️</button>
                            <button class="btn btn-outline-danger btn-delete-address" data-address-id="${addr.id}" title="Удалить">🗑️</button>
                        </div>
                    </div>
                </div>
            `;

            container.appendChild(card);
        });

        // Re-attach event listeners
        $$('.btn-edit-address').forEach(btn => {
            btn.addEventListener('click', () => openEditModal(btn.dataset.addressId));
        });
        $$('.btn-delete-address').forEach(btn => {
            btn.addEventListener('click', () => openDeleteModal(btn.dataset.addressId));
        });
    }

    /* ==================== Notification ==================== */
    function showNotification(message, type = 'info') {
        // Remove existing notifications
        const existing = document.querySelector('.delivery-address-notification');
        if (existing) existing.remove();

        const notification = document.createElement('div');
        notification.className = `alert alert-${type} delivery-address-notification position-fixed`;
        notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);';
        notification.textContent = message;

        document.body.appendChild(notification);

        // Animate in
        setTimeout(() => {
            notification.style.opacity = '1';
        }, 10);

        // Auto remove
        setTimeout(() => {
            notification.style.opacity = '0';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    /* ==================== Utility ==================== */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /* ==================== Init ==================== */
    function init(addresses = []) {
        state.addresses = addresses;
        initAutocomplete();
        initModals();
        renderAddresses();
    }

    return { init };
})();

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    // Load addresses from template context
    const addressesData = window.PROFILE_ADDRESSES || [];
    DeliveryAddressManager.init(addressesData);
});
