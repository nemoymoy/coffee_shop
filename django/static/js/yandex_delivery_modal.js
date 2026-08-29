/**
 * Coffee Shop — Yandex Delivery Modal Widget (Refactored).
 *
 * Чистая архитектура с разделением ответственности:
 * - state: централизованное управление состоянием
 * - config: константы
 * - api: все HTTP запросы
 * - ui: DOM манипуляции, навигация по шагам, управление модалкой
 * - map: инициализация Яндекс Карт, метки, события
 * - autocomplete: автокомплит адреса
 * - validation: валидация формы
 * - delivery: обновление сводки доставки
 */
const YandexDeliveryWidget = (() => {

    /* ==================== State ==================== */
    const state = {
        selectedType: null,       // 'courier' | 'pvz' | 'postomat'
        selectedAddress: '',
        selectedCoords: [],
        selectedPvzId: '',
        selectedPvzName: '',
        estimatedCost: 0,
        step: 1,
        ymapsLoaded: false,
        ymapsReady: false,
        mapInstance: null,
        selectedPlacemark: null,
        pvzPoints: [],
        bootstrapModal: null,
        visible: false,
        debounceTimer: null,
        autocompleteIndex: -1,
        suggestions: [],
    };

    /* ==================== Config ==================== */
    const CONFIG = {
        CALCULATE_DELIVERY_URL: '/checkout/calculate-delivery/',
        GEOCODE_URL: '/checkout/geocode-address/',
        PVZ_LOCATIONS_URL: '/checkout/pvz-locations/',
        DEBOUNCE_MS: 600,
        SHOP_LAT: window.YANDEX_SHOP_LAT ?? 53.216940239129094,
        SHOP_LON: window.YANDEX_SHOP_LON ?? 50.162688008923745,
    };

    /* ==================== Cart State ==================== */
    const cartState = {
        items: [],  // [{product_id, weight, quantity, price}]
        packages: [],  // [{weight_range, length, width, height, tare_weight}]
        packagesLoaded: false,
    };

    /* ==================== Tare Package Management ==================== */
    async function loadPackagesFromAPI() {
        if (cartState.packagesLoaded) return;
        try {
            const result = await apiGet('/checkout/packages/');
            if (result.success && result.packages?.length) {
                cartState.packages = result.packages;
                cartState.packagesLoaded = true;
                console.log('[YandexDelivery] Packages loaded from API:', cartState.packages);
            }
        } catch (err) {
            console.error('[YandexDelivery] Failed to load packages:', err);
        }
    }

    /**
     * Определяет тара по весу товара используя данные из БД.
     */
    function findPackageForWeight(weightGrams) {
        if (weightGrams <= 100) {
            return cartState.packages.find(p => p.weight_range === 'light');
        } else if (weightGrams <= 500) {
            return cartState.packages.find(p => p.weight_range === 'medium');
        } else if (weightGrams <= 2000) {
            return cartState.packages.find(p => p.weight_range === 'heavy');
        } else if (weightGrams <= 5000) {
            return cartState.packages.find(p => p.weight_range === 'xl');
        } else {
            return cartState.packages.find(p => p.weight_range === 'xxl');
        }
    }

    /* ==================== Cart from Page ==================== */
    function loadCartFromPage() {
        cartState.items = [];

        // Ищем элементы корзины в правой колонке (карточка "Ваш заказ")
        const orderCard = document.querySelector('.col-md-4 .card-body');
        if (!orderCard) {
            console.warn('[YandexDelivery] Order card not found');
            return cartState.items;
        }

        // Пропускаем первую строку (итого за товары), берём элементы товаров
        const rows = orderCard.querySelectorAll('.d-flex.justify-content-between');
        let itemIndex = 0;

        rows.forEach((row, index) => {
            // Пропускаем заголовок "Ваш заказ" и строки итогов (Стоимость товаров, Доставка, Итого)
            // Строки товаров содержат <strong>название товара</strong> и <small>вес г</small>
            const strongEl = row.querySelector('strong');
            const smallEl = row.querySelector('small');

            if (!strongEl) return; // Это не строка товара (заголовок или итого)

            const weightMatch = smallEl ? smallEl.textContent.match(/(\d+)/) : null;
            const weight = weightMatch ? parseInt(weightMatch[1]) : 250;

            const priceText = row.querySelector('span:last-child')?.textContent || '0';
            const price = parseFloat(priceText.replace(/[\s₽]/g, '').replace(',', '.')) || 0;

            cartState.items.push({
                product_id: 'temp_' + itemIndex,
                weight: weight,
                quantity: 1,
                price: price,
            });
            itemIndex++;
        });

        console.log('[YandexDelivery] Cart loaded from page:', cartState.items);
        return cartState.items;
    }

    /**
     * Рассчитывает общее количество товаров и общий вес для отображения в карточке расчета.
     * Сначала суммирует вес всех товаров, затем выбирает ОДНУ тару для суммарного веса.
     */
    function getCartSummary() {
        const totalItems = cartState.items.reduce((sum, item) => sum + item.quantity, 0);
        
        // 1. Суммируем вес всех товаров
        let totalProductWeightGrams = 0;
        for (const item of cartState.items) {
            totalProductWeightGrams += item.weight * item.quantity;
        }
        
        // 2. Выбираем ОДНУ тару для суммарного веса
        const package = findPackageForWeight(totalProductWeightGrams);
        const tareWeightGrams = package ? parseFloat(package.tare_weight) * 1000 : 0;
        
        // 3. Общий вес = вес товаров + вес тары
        return { totalItems, totalWeight: totalProductWeightGrams + tareWeightGrams };
    }

    /* ==================== API Layer ==================== */

    async function apiPost(url, body) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': YandexDeliveryUtils.getCsrfToken(),
            },
            body: JSON.stringify(body),
        });
        const text = await response.text();
        try {
            return JSON.parse(text);
        } catch {
            console.error('[YandexDelivery] Server returned non-JSON:', text.substring(0, 200));
            return { success: false, error: 'Ошибка сервера' };
        }
    }

    async function apiGet(url) {
        const response = await fetch(url, {
            headers: {
                'X-CSRFToken': YandexDeliveryUtils.getCsrfToken(),
            },
        });
        return response.json();
    }

    async function geocodeAddress(query) {
        if (!query || query.length < 3) {
            return { success: false, error: 'Слишком короткий запрос' };
        }
        try {
            const data = await apiPost(CONFIG.GEOCODE_URL, { query });
            if (data.rate_limited || data.api_error) {
                return { success: false, error: 'Сервис геокодинга временно недоступен' };
            }
            if (!data.success || !data.features?.length) {
                return { success: false, error: 'Адрес не найден' };
            }
            return { success: true, features: data.features };
        } catch (err) {
            console.error('[YandexDelivery] Geocode error:', err);
            return { success: false, error: 'Сетевая ошибка' };
        }
    }

    async function calculateDelivery(coords, address, deliveryType, pvzId) {
        try {
            // Load cart items from DOM if not already loaded
            if (cartState.items.length === 0) {
                loadCartFromPage();
            }
            // Load packages from API if not already loaded
            if (!cartState.packagesLoaded) {
                await loadPackagesFromAPI();
            }

            const payload = {
                destination_coords: coords,
                destination_address: address,
                pvz_id: pvzId || null,
                delivery_type: deliveryType === 'pvz' ? 'pickup' : (deliveryType || 'courier'),
                cart_items: cartState.items,
            };

            // Логирование данных для отладки расчета доставки
            console.log('[YandexDelivery] === Данные для расчета доставки ===');
            console.log('[YandexDelivery] Тип доставки:', payload.delivery_type);
            console.log('[YandexDelivery] Координаты:', payload.destination_coords);
            console.log('[YandexDelivery] Адрес:', payload.destination_address);
            console.log('[YandexDelivery] ПВЗ ID:', payload.pvz_id);
            console.log('[YandexDelivery] Товары в корзине:');
            cartState.items.forEach((item, i) => {
                console.log(`  Товар №${i + 1}: ${item.weight}г`);
            });
            const summary = getCartSummary();
            const totalProductWeight = cartState.items.reduce((sum, item) => sum + item.weight * item.quantity, 0);
            const tare = findPackageForWeight(totalProductWeight);
            const tareWeightGrams = tare ? parseFloat(tare.tare_weight) * 1000 : 0;
            console.log('[YandexDelivery] Вес тары:', tareWeightGrams, 'г');
            const totalPackageWeightGrams = totalProductWeight + tareWeightGrams;
            console.log('[YandexDelivery] Вес посылки (товары + тара):', totalPackageWeightGrams, 'г');
            if (tare) {
                console.log('[YandexDelivery] Размеры посылки:', `${tare.length}x${tare.width}x${tare.height} м`);
            }
            console.log('[YandexDelivery] ==========================================');

            const data = await apiPost(CONFIG.CALCULATE_DELIVERY_URL, payload);
            if (data.success && data.price != null) {
                return { success: true, price: data.price, delivery_days: data.delivery_days };
            }
            return { success: false, error: data.error || 'Не удалось рассчитать стоимость' };
        } catch (err) {
            console.error('[YandexDelivery] Calculate error:', err);
            return { success: false, error: 'Сетевая ошибка' };
        }
    }

    async function loadPvzPoints(type) {
        try {
            let data;
            if (type === 'postomat') {
                // Для постоматов используем отдельный endpoint
                data = await apiGet('/checkout/postamats/');
            } else {
                // Для ПВЗ используем стандартный endpoint
                data = await apiGet(`${CONFIG.PVZ_LOCATIONS_URL}?type=pvz`);
            }

            if (!data.success || !data.points?.length) {
                return { success: false };
            }

            return { success: true, points: data.points };
        } catch (err) {
            console.error('[YandexDelivery] Load PVZ error:', err);
            return { success: false };
        }
    }

    /* ==================== DOM Helpers ==================== */
    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => document.querySelectorAll(selector);
    const show = (el) => el?.classList.remove('d-none');
    const hide = (el) => el?.classList.add('d-none');

    /* ==================== Modal Management ==================== */
    function initModal() {
        const modalEl = $('#deliveryModal');
        if (!modalEl) {
            console.log('[YandexDelivery] No modal found, skipping (only needed on checkout page)');
            return;
        }

        if (typeof bootstrap === 'undefined' || !bootstrap.Modal) {
            console.warn('[YandexDelivery] Bootstrap Modal not available');
            return;
        }

        state.bootstrapModal = new bootstrap.Modal(modalEl, { backdrop: true, keyboard: true });

        modalEl.addEventListener('show.bs.modal', () => {
            resetState();
            goToStep(1);
        });

        modalEl.addEventListener('hidden.bs.modal', () => {
            resetState();
            state.visible = false;
        });

        // Выбор типа доставки (делегирование на модальное окно)
        const step1Container = modalEl.querySelector('#deliveryStep1');
        step1Container?.addEventListener('change', (e) => {
            if (e.target.matches('input[name="yandex_delivery_type"]')) {
                state.selectedType = e.target.value;
                goToStep(2);
                updateConfirmButton();
            }
        });

        // Автокомплит
        initAutocomplete();

        // Подтверждение
        $('#confirmDeliveryBtn')?.addEventListener('click', handleConfirm);

        // Кнопка открытия
        $('#openDeliveryModal')?.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });

        state.visible = true;
    }

    function openModal() {
        state.bootstrapModal?.show();
    }

    function closeModal() {
        state.bootstrapModal?.hide();
    }

    function goToStep(stepNumber) {
        state.step = stepNumber;
        const step1 = $('#deliveryStep1');
        const step2 = $('#deliveryStep2');
        const step3 = $('#deliveryStep3');
        const widgetContainer = $('#yandexDeliveryWidgetContainer');
        const addressInputWrap = $('#yandexAddressInputWrap');
        const mapWarning = $('#mapUnavailableWarning');

        hide(step1);
        hide(step2);
        hide(step3);

        if (stepNumber === 1) {
            show(step1);
        } else if (stepNumber === 2) {
            show(step2);
            if (state.selectedType === 'courier') {
                hide(widgetContainer);
                hide(mapWarning);
                hide($('#selectedPvzInfo'));
                show(addressInputWrap);
            } else {
                hide(addressInputWrap);
                hide(mapWarning);
                show(widgetContainer);
                hide($('#selectedPvzInfo'));
                loadYmaps();
            }
        } else if (stepNumber === 3) {
            if (state.selectedType === 'courier') {
                show(step2);
                hide(widgetContainer);
                show(addressInputWrap);
                hide($('#selectedPvzInfo'));
            } else {
                show(step3);
                // Карта остается видимой из шага 2 — не скрываем widgetContainer
                
                // Заполняем детали расчета
                const calcAddress = $('#calcAddress');
                const calcPvzBlock = $('#calcPvzBlock');
                const calcPvzName = $('#calcPvzName');
                const calcDeliveryType = $('#calcDeliveryType');
                const calcItemDetails = $('#calcItemDetails');
                
                if (calcAddress) calcAddress.textContent = state.selectedAddress;
                
                if (calcDeliveryType) {
                    const typeLabels = {
                        pvz: '📦 Пункт выдачи (ПВЗ)',
                        postomat: '📮 Постомат',
                    };
                    calcDeliveryType.textContent = typeLabels[state.selectedType] || typeLabels.pvz;
                }
                
                if (calcItemDetails) {
                    if (cartState.packagesLoaded) {
                        const summary = getCartSummary();
                        calcItemDetails.textContent = `${summary.totalItems} шт, ${summary.totalWeight} г`;
                    } else {
                        // Fallback: show only product weight if packages not loaded
                        const summary = getCartSummary();
                        calcItemDetails.textContent = `${summary.totalItems} шт, ${summary.totalWeight} г`;
                    }
                }
                
                if (state.selectedPvzName && calcPvzName) {
                    calcPvzName.textContent = state.selectedPvzName + (state.selectedAddress ? ' — ' + state.selectedAddress : '');
                    if (calcPvzBlock) show(calcPvzBlock);
                } else if (calcPvzBlock) {
                    hide(calcPvzBlock);
                }
            }
        }
    }

    function resetState() {
        state.selectedType = null;
        state.selectedAddress = '';
        state.selectedCoords = [];
        state.selectedPvzId = '';
        state.selectedPvzName = '';
        state.estimatedCost = 0;
        state.step = 1;
        destroyMap();

        $$('.form-check input[name="yandex_delivery_type"]').forEach(r => r.checked = false);

        const addressInput = $('#yandexAddressInput');
        if (addressInput) addressInput.value = '';

        const autocompleteList = $('#yandexAutocompleteList');
        if (autocompleteList) {
            autocompleteList.innerHTML = '';
            hide(autocompleteList);
        }

        const courierPriceBlock = $('#courierPriceBlock');
        if (courierPriceBlock) {
            courierPriceBlock.innerHTML = '';
            courierPriceBlock.style.display = 'none';
            courierPriceBlock.classList.remove('border-danger');
        }

        const costEl = $('#widgetCost');
        if (costEl) costEl.textContent = 'Расчёт...';

        const confirmBtn = $('#confirmDeliveryBtn');
        if (confirmBtn) confirmBtn.disabled = true;

        hide($('#deliveryModalError'));
    }

    /* ==================== Autocomplete ==================== */
    function initAutocomplete() {
        const addressInput = $('#yandexAddressInput');
        const autocompleteList = $('#yandexAutocompleteList');
        if (!addressInput) return;

        addressInput.addEventListener('input', () => {
            state.autocompleteIndex = -1;
            const query = addressInput.value.trim();

            if (state.debounceTimer) clearTimeout(state.debounceTimer);

            if (query.length < 3) {
                hide(autocompleteList);
                state.suggestions = [];
                return;
            }

            state.debounceTimer = setTimeout(() => fetchSuggestions(query), CONFIG.DEBOUNCE_MS);
        });

        addressInput.addEventListener('keydown', (e) => {
            const items = autocompleteList?.querySelectorAll('.autocomplete-item');
            if (!items?.length) return;

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    state.autocompleteIndex = Math.min(state.autocompleteIndex + 1, items.length - 1);
                    updateSelection(items);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    state.autocompleteIndex = Math.max(state.autocompleteIndex - 1, 0);
                    updateSelection(items);
                    break;
                case 'Enter':
                    e.preventDefault();
                    const idx = state.autocompleteIndex >= 0 ? state.autocompleteIndex : 0;
                    if (items[idx]) items[idx].click();
                    break;
                case 'Escape':
                    hide(autocompleteList);
                    break;
            }
        });

        autocompleteList?.addEventListener('click', (e) => {
            const item = e.target.closest('.autocomplete-item');
            if (item?.dataset.index !== undefined) {
                const feature = state.suggestions[+item.dataset.index];
                if (feature) selectAutocompleteItem(feature);
            }
        });

        document.addEventListener('click', (e) => {
            if (!autocompleteList?.contains(e.target) && e.target !== addressInput) {
                hide(autocompleteList);
            }
        });
    }

    function updateSelection(items) {
        items.forEach((item, i) => {
            item.classList.toggle('selected', i === state.autocompleteIndex);
        });
    }

    async function fetchSuggestions(query) {
        const autocompleteList = $('#yandexAutocompleteList');
        if (!autocompleteList) return;

        autocompleteList.innerHTML = '<div class="autocomplete-item text-muted">Поиск...</div>';
        show(autocompleteList);

        const result = await geocodeAddress(query);

        if (!result.success) {
            autocompleteList.innerHTML = `<div class="autocomplete-item text-warning">⚠️ ${result.error}. Введите вручную.</div>`;
            state.suggestions = [];
            return;
        }

        state.suggestions = result.features;
        autocompleteList.innerHTML = '';

        state.suggestions.forEach((feature, i) => {
            const item = document.createElement('div');
            item.className = 'autocomplete-item';
            item.textContent = feature.text;
            item.dataset.index = i;
            autocompleteList.appendChild(item);
        });
    }

    function selectAutocompleteItem(feature) {
        const addressInput = $('#yandexAddressInput');
        if (addressInput) addressInput.value = feature.text;
        state.selectedAddress = feature.text;

        hide($('#yandexAutocompleteList'));
        state.suggestions = [];
        state.autocompleteIndex = -1;

        geocodeAndCalculate(feature.text, feature.coords);
    }
    /* ==================== Geocode & Calculate ==================== */
    async function geocodeAndCalculate(address, initialCoords) {
        const costEl = $('#widgetCost');
        const etaEl = $('#widgetEta');
        const etaLabelEl = $('#widgetEtaLabel');
        const confirmBtn = $('#confirmDeliveryBtn');
        const courierPriceBlock = $('#courierPriceBlock');

        if (state.selectedType === 'courier' && courierPriceBlock) {
            show(courierPriceBlock);
            courierPriceBlock.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Расчёт...';
        } else if (costEl) {
            YandexDeliveryUtils.showLoading(costEl);
        }

        let result = await geocodeAddress(address);
        if (!result.success) {
            showAddrError(costEl, confirmBtn, courierPriceBlock, result.error);
            return;
        }

        const feature = result.features[0];
        let coords = feature.coords || initialCoords;
        const addr = feature.text || address;

        if (!coords || coords.length < 2) {
            showAddrError(costEl, confirmBtn, courierPriceBlock, 'Нет координат. Укажите адрес подробнее.');
            return;
        }

        state.selectedCoords = coords;
        state.selectedAddress = addr;

        YandexDeliveryUtils.showLoading(costEl);
        const calc = await calculateDelivery(coords.join(','), addr, state.selectedType, state.selectedPvzId);

        if (calc.success && calc.price != null) {
            state.estimatedCost = calc.price;
            renderCalcResult(costEl, etaEl, etaLabelEl, courierPriceBlock, confirmBtn, calc);
        } else {
            showDeliveryError(costEl, courierPriceBlock, calc.error);
        }
    }

    function renderCalcResult(costEl, etaEl, etaLabelEl, courierPriceBlock, confirmBtn, calc) {
        if (state.selectedType === 'courier' && courierPriceBlock) {
            const etaText = YandexDeliveryUtils.showEtaText(calc.delivery_days);
            courierPriceBlock.innerHTML = `✅ Стоимость доставки: <strong>${YandexDeliveryUtils.formatPrice(calc.price)} ₽</strong>${etaText}`;
            courierPriceBlock.classList.remove('border-danger');
        } else {
            YandexDeliveryUtils.setTextContent(costEl, `${YandexDeliveryUtils.formatPrice(calc.price)} ₽`);
            YandexDeliveryUtils.setTextContent(etaEl, calc.delivery_days ? `(${calc.delivery_days} дн.)` : '');
            YandexDeliveryUtils.setTextContent(etaLabelEl, calc.delivery_days ? ` ETA: ${calc.delivery_days} дн.` : ' ETA: ');
        }
        updateConfirmButton();
        if (state.selectedType !== 'courier') goToStep(3);
    }

    function showAddrError(costEl, confirmBtn, courierPriceBlock, msg) {
        const html = `<span class="text-danger">❌ ${msg}</span>`;
        if (state.selectedType === 'courier' && courierPriceBlock) {
            courierPriceBlock.innerHTML = html;
            courierPriceBlock.classList.add('border-danger');
        } else if (costEl) {
            costEl.innerHTML = html;
        }
        if (confirmBtn) confirmBtn.disabled = true;
    }

    function showDeliveryError(costEl, courierPriceBlock, msg) {
        console.error('[YandexDelivery] Delivery error:', msg);
        const html = `<span class="text-danger">❌ ${msg}</span>`;
        if (state.selectedType === 'courier' && courierPriceBlock) {
            courierPriceBlock.innerHTML = html;
            courierPriceBlock.classList.add('border-danger');
        } else if (costEl) {
            costEl.innerHTML = html;
        }
    }

    /* ==================== Confirm Selection ==================== */
    function handleConfirm() {
        const errors = [];
        if (!state.selectedType) errors.push('Выберите способ доставки');
        if (state.selectedType !== 'courier' && !state.selectedPvzId) errors.push('Выберите пункт выдачи или постомат');
        if (!state.selectedCoords.length) errors.push('Координаты не получены');
        if (!state.selectedAddress) errors.push('Введите адрес доставки');
        if (state.estimatedCost <= 0) errors.push('Не удалось рассчитать стоимость');

        if (errors.length) {
            showError(errors.join(' '));
            return;
        }

        clearError();

        YandexDeliveryUtils.setFieldValue('id_delivery_address', state.selectedAddress);
        YandexDeliveryUtils.setFieldValue('id_yandex_delivery_type', state.selectedType);
        YandexDeliveryUtils.setFieldValue('id_yandex_station_id', state.selectedPvzId);
        YandexDeliveryUtils.setFieldValue('id_yandex_station_name', state.selectedPvzName || state.selectedAddress);
        YandexDeliveryUtils.setFieldValue('id_yandex_delivery_cost', state.estimatedCost);

        const checkoutAddr = $('#id_delivery_address');
        if (checkoutAddr) checkoutAddr.value = state.selectedAddress;

        updateDeliverySummary();
        closeModal();
    }

    function showError(msg) {
        const el = $('#deliveryModalError');
        if (el) {
            el.textContent = msg;
            el.style.display = 'block';
        }
    }

    function clearError() {
        const el = $('#deliveryModalError');
        if (el) {
            el.textContent = '';
            el.style.display = 'none';
        }
    }

    /* ==================== Delivery Summary ==================== */
    function updateDeliverySummary() {
        const deliveryInfo = $('#deliveryInfo');
        if (!deliveryInfo) return;

        const typeLabels = {
            courier: '🚗 Курьер',
            pvz: '📦 Пункт выдачи (ПВЗ)',
            postomat: '📮 Постомат',
        };

        const typeEl = $('#selectedDeliveryType');
        const addrEl = $('#selectedDeliveryAddress');
        const costEl = $('#selectedDeliveryCost');
        const etaEl = $('#selectedDeliveryEta');
        const orderCost = $('#orderDeliveryCost');
        const goodsTotal = $('#orderGoodsTotal');
        const checkoutTotal = $('#checkoutTotal');

        if (typeEl) typeEl.textContent = typeLabels[state.selectedType] || typeLabels.courier;
        if (addrEl) addrEl.textContent = state.selectedAddress;
        if (costEl) costEl.textContent = `${YandexDeliveryUtils.formatPrice(state.estimatedCost)} ₽`;
        if (etaEl) etaEl.textContent = '';

        show(deliveryInfo);

        if (orderCost) {
            orderCost.textContent = state.estimatedCost
                ? `${YandexDeliveryUtils.formatPrice(state.estimatedCost)} ₽`
                : '— ₽';
        }

        if (goodsTotal && checkoutTotal && state.estimatedCost > 0) {
            // Парсим стоимость товаров из текста (может быть в формате '150,00 ₽' или '150.00 ₽')
            const goodsText = goodsTotal.textContent
                .replace(/[^0-9.,]/g, '')           // оставляем только цифры, точки и запятые
                .replace(/\./g, '')                  // убираем разделитель тысяч
                .replace(',', '.');                  // запятую заменяем на точку
            const goods = parseFloat(goodsText) || 0;

            // Гарантируем что estimatedCost — число
            const deliveryCost = typeof state.estimatedCost === 'string'
                ? parseFloat(state.estimatedCost) || 0
                : state.estimatedCost;

            const newTotal = goods + deliveryCost;
            checkoutTotal.textContent = `${YandexDeliveryUtils.formatPrice(newTotal)} ₽`;
        }
    }

    function updateConfirmButton() {
        const btn = $('#confirmDeliveryBtn');
        if (btn) btn.disabled = !(state.selectedType && state.estimatedCost > 0);
    }
    /* ==================== YMaps Integration ==================== */
    function loadYmaps() {
        if (state.ymapsLoaded) {
            initMap();
            return;
        }

        // Check if already loaded via base.html
        if (window.ymaps) {
            console.log('[YandexDelivery] ymaps already loaded');
            state.ymapsLoaded = true;
            // Wait for container to be visible
            const widgetContainer = $('#yandexDeliveryWidgetContainer');
            if (widgetContainer && widgetContainer.classList.contains('d-none')) {
                console.warn('[YandexDelivery] Widget container is hidden, waiting for visibility');
                setTimeout(loadYmaps, 200);
                return;
            }
            setTimeout(initMap, 100);
            return;
        }

        const apiKey = window.YANDEX_JAVASCRIPT_API_KEY;
        if (!apiKey) {
            console.error('[YandexDelivery] No API key');
            showMapError('Не настроен API-ключ Яндекс Карт');
            return;
        }

        console.log('[YandexDelivery] Loading YMaps API 2.1...');
        const script = document.createElement('script');
        script.id = 'yandex-maps-api-script';
        script.src = `https://api-maps.yandex.ru/2.1/?apikey=${apiKey}&lang=ru_RU`;
        script.async = true;

        script.onload = () => {
            console.log('[YandexDelivery] YMaps API 2.1 loaded');
            state.ymapsLoaded = true;
            const widgetContainer = $('#yandexDeliveryWidgetContainer');
            if (widgetContainer && widgetContainer.classList.contains('d-none')) {
                console.warn('[YandexDelivery] Widget container is hidden, waiting for visibility');
                setTimeout(loadYmaps, 200);
                return;
            }
            if (typeof ymaps !== 'undefined' && ymaps.ready) {
                ymaps.ready(initMap);
            } else {
                setTimeout(initMap, 500);
            }
        };

        script.onerror = () => {
            console.error('[YandexDelivery] Failed to load YMaps API');
            showMapError('Не удалось загрузить Яндекс Карты. Введите адрес вручную.');
        };

        document.head.appendChild(script);
    }

    function initMap() {
        if (typeof ymaps === 'undefined') {
            setTimeout(initMap, 200);
            return;
        }

        const container = $('#delivery-widget');
        if (!container) {
            console.error('[YandexDelivery] #delivery-widget not found');
            return;
        }

        destroyMap();

        try {
            const lat = CONFIG.SHOP_LAT;
            const lon = CONFIG.SHOP_LON;
            console.log('[YandexDelivery] Creating map at', [lat, lon]);

            state.mapInstance = new ymaps.Map(container, {
                center: [lat, lon],
                zoom: 14,
                controls: ['zoomControl', 'fullscreenControl'],
            }, { suppressMapOpenBlock: true });

            // Метка магазина
            const shop = new ymaps.Placemark([lat, lon], {
                hintContent: 'Магазин: ул. Революционная, д. 3',
                balloonContent: '📍 Магазин',
            }, { preset: 'islands#darkOrangeCircleIcon' });
            state.mapInstance.geoObjects.add(shop);

            // Клик по карте
            state.mapInstance.events.add('click', onMapClick);

            // Загружаем ПВЗ
            loadPvzOnMap();

            state.ymapsReady = true;
            console.log('[YandexDelivery] Map created');
        } catch (e) {
            console.error('[YandexDelivery] Map creation failed:', e);
            showMapError('Не удалось инициализировать карту');
        }
    }

    function createMapPlacemark(lat, lon, options) {
        return new ymaps.Placemark([lat, lon], {
            hintContent: options.hintContent || '',
            balloonContent: options.balloonContent || '',
        }, { preset: options.preset || 'islands#darkOrangeIcon' });
    }

    function destroyMap() {
        if (state.mapInstance) {
            try {
                // YMaps 2.1 uses destroy(), 3.0 uses dispose()
                state.mapInstance.destroy ? state.mapInstance.destroy() : state.mapInstance.dispose();
            } catch (e) {
                console.warn('[YandexDelivery] Map destroy error:', e);
            }
            state.mapInstance = null;
        }
    }

    function onMapClick(e) {
        const coords = e.get('coords');
        if (!coords || !Array.isArray(coords) || coords.length < 2) return;
        console.log('[YandexDelivery] Map clicked at', coords);

        ymaps.geocode(coords.join(',')).then((res) => {
            const first = res.geoObjects.get(0);
            if (!first) return;
            const address = first.properties.get('fullName') || first.properties.get('text');
            onReverseGeocode(address, coords);
        }).catch((err) => console.error('[YandexDelivery] Reverse geocode error:', err));
    }

    function onReverseGeocode(address, coords) {
        if (state.selectedPlacemark && state.mapInstance) {
            state.mapInstance.geoObjects.remove(state.selectedPlacemark);
        }

        state.selectedPlacemark = new ymaps.Placemark(coords, {
            hintContent: address,
            balloonContent: '✅ Выберите этот адрес',
        }, { preset: 'islands#orangeCircleDotIcon' });
        state.mapInstance.geoObjects.add(state.selectedPlacemark);

        handlePointSelected({
            id: '',
            name: 'Выбранный адрес',
            address: address,
            coordinates: coords,
        });
    }

    async function loadPvzOnMap() {
        const costEl = $('#widgetCost');
        const originalText = costEl?.textContent || '';

        // Определяем тип точек для загрузки
        const pointType = state.selectedType === 'postomat' ? 'postomat' : 'pvz';
        const pointLabel = state.selectedType === 'postomat' ? 'Постоматы' : 'ПВЗ';

        console.log('[YandexDelivery] loadPvzOnMap: selectedType=', state.selectedType, 'pointType=', pointType);

        if (costEl) costEl.textContent = `Загрузка ${pointLabel}...`;

        const data = await loadPvzPoints(pointType);
        if (costEl) costEl.textContent = originalText;

        if (!data.success || !data.points?.length) {
            console.warn('[YandexDelivery] No', pointLabel, '(selectedType:', state.selectedType + ')');
            showMapError(`${pointLabel} временно недоступны`);
            return;
        }

        console.log('[YandexDelivery] Loaded', data.points.length, pointLabel);

        state.pvzPlacemarks = [];

        data.points.forEach((point) => {
            if (!point.latitude || !point.longitude) return;

            const placemark = new ymaps.Placemark([point.latitude, point.longitude], {
                hintContent: point.name,
                balloonContent: `<strong>${YandexDeliveryUtils.escapeHtml(point.name)}</strong><br>${YandexDeliveryUtils.escapeHtml(point.address)}`,
            }, { preset: state.selectedType === 'postomat' ? 'islands#darkBlueCircleIcon' : 'islands#darkGreenCircleIcon' });

            placemark.events.add('click', () => {
                console.log('[YandexDelivery] Point clicked:', point.name);
                // Используем полное описание адреса
                const pointLabelFull = point.name + (point.address ? ' — ' + point.address : '');
                handlePointSelected({
                    id: point.id,
                    name: point.name,
                    address: point.address || pointLabelFull,
                    fullAddress: pointLabelFull,
                    coordinates: [point.longitude, point.latitude],
                });
            });

            state.pvzPlacemarks.push(placemark);
            if (state.mapInstance) {
                state.mapInstance.geoObjects.add(placemark);
            }
        });

        try {
            // Центрируем карту по магазину без анимации
            state.mapInstance.options.set('center', [CONFIG.SHOP_LON, CONFIG.SHOP_LAT]);
            state.mapInstance.options.set('zoom', 16);
        } catch (e) {
            console.warn('[YandexDelivery] setCenter error:', e);
        }
    }

    function showMapError(message) {
        const warning = $('#mapUnavailableWarning');
        if (warning) {
            const p = warning.querySelector('p');
            if (p) p.textContent = message + ' Введите адрес вручную.';
            show(warning);
        }
        hide($('#yandexDeliveryWidgetContainer'));
        show($('#yandexAddressInputWrap'));
    }
    /* ==================== Point Selection ==================== */
    function handlePointSelected(point) {
        console.log('[YandexDelivery] Point selected:', point);

        state.selectedPvzId = point.id || '';
        state.selectedPvzName = point.name || '';
        // Используем fullAddress если доступен (для ПВЗ), иначе address
        state.selectedAddress = point.fullAddress || point.address || state.selectedPvzName;

        const coords = point.coordinates;
        state.selectedCoords = Array.isArray(coords)
            ? coords
            : (typeof coords === 'string' ? coords.split(',').map(Number) : []);

        const costEl = $('#widgetCost');
        const confirmBtn = $('#confirmDeliveryBtn');
        const addressInput = $('#yandexAddressInput');
        const pvzNameEl = $('#selectedPvzNameDisplay');
        const pvzInfoBlock = $('#selectedPvzInfo');

        YandexDeliveryUtils.showLoading(costEl);
        if (confirmBtn) confirmBtn.disabled = true;

        // Заполняем строку поиска адресом ПВЗ
        if (addressInput) {
            addressInput.value = state.selectedAddress;
        }

        // Показываем блок с информацией о выбранном ПВЗ
        if (pvzNameEl) {
            pvzNameEl.textContent = state.selectedAddress;
        }

        // Запускаем расчет стоимости доставки
        calculateDeliveryCost(state.selectedCoords.join(','), state.selectedAddress);
    }

    async function calculateDeliveryCost(coords, address) {
        const costEl = $('#widgetCost');
        const etaEl = $('#widgetEta');
        const etaLabelEl = $('#widgetEtaLabel');
        const confirmBtn = $('#confirmDeliveryBtn');

        const calc = await calculateDelivery(coords, address, state.selectedType, state.selectedPvzId);

        if (calc.success && calc.price != null) {
            state.estimatedCost = calc.price;
            YandexDeliveryUtils.setTextContent(costEl, `${YandexDeliveryUtils.formatPrice(calc.price)} ₽`);
            YandexDeliveryUtils.setTextContent(etaEl, calc.delivery_days ? `(${calc.delivery_days} дн.)` : '');
            YandexDeliveryUtils.setTextContent(etaLabelEl, calc.delivery_days ? ` ETA: ${calc.delivery_days} дн.` : ' ETA: ');
            updateConfirmButton();
            
            // Показываем блок с информацией о выбранном ПВЗ
            if (state.selectedType === 'pvz' || state.selectedType === 'postomat') {
                const pvzInfo = $('#selectedPvzInfo');
                const pvzNameEl = $('#selectedPvzNameDisplay');
                if (pvzInfo && pvzNameEl && state.selectedPvzName) {
                    pvzNameEl.textContent = state.selectedAddress;
                    show(pvzInfo);
                }
            }
            
            goToStep(3);
        } else {
            YandexDeliveryUtils.setTextContent(costEl, calc.error || 'Не удалось рассчитать');
            if (confirmBtn) confirmBtn.disabled = true;
        }
    }

    /* ==================== PostMessage Listener ==================== */
    function initPostMessage() {
        window.addEventListener('message', (e) => {
            const TRUSTED_ORIGINS = [
                'https://dostavka.yandex.ru',
                'https://delivery.yandex.ru',
                'https://www.yandex.ru',
            ];

            if (!TRUSTED_ORIGINS.includes(e.origin)) return;

            const data = e.data;
            if (!data) return;

            const point = {
                id: data.pointId || data.point_id || data.id || '',
                name: data.name || data.title || data.pointName || '',
                address: data.address || data.full_address || '',
                coordinates: data.coordinates || data.coords || data.center || '',
            };

            if (point.id) {
                console.log('[YandexDelivery] Point via postMessage:', point);
                handlePointSelected(point);
            }
        });
    }



    /* ==================== Init ==================== */
    function init() {
        initModal();
        initPostMessage();
        
        // Load cart items and packages when modal opens
        const modalEl = document.getElementById('deliveryModal');
        if (modalEl) {
            modalEl.addEventListener('show.bs.modal', () => {
                if (cartState.items.length === 0) {
                    loadCartFromPage();
                }
                loadPackagesFromAPI();
            });
        }
    }

    /* ==================== Public API ==================== */
    return {
        init,
        openModal,
        closeModal,
        getSelectedType: () => state.selectedType,
        getSelectedAddress: () => state.selectedAddress,
        getEstimatedCost: () => state.estimatedCost,
        _handlePointSelected: handlePointSelected,
    };

})();

document.addEventListener('DOMContentLoaded', YandexDeliveryWidget.init);

/**
 * Callback for Yandex Delivery widget (postMessage fallback).
 */
window.YandexDeliveryCallback = function (pointData) {
    console.log('[YandexDelivery] Callback:', pointData);
    const point = {
        id: pointData.pointId || pointData.id || '',
        name: pointData.name || pointData.title || '',
        address: pointData.address || pointData.full_address || '',
    };
    if (point.id) {
        YandexDeliveryWidget._handlePointSelected(point);
    }
};
