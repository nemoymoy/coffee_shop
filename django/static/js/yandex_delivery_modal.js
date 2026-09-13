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
        selectedWorkSchedule: '', // График работы постомата
        selectedDistance: null,   // Расстояние до постомата (км)
        selectedOfferId: '',      // offer_id from offers/info
        expressClaimId: '',       // ID заявки Express API
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
        // Новая логика
        deliveryOrderCreated: false,  // true когда заказ создан в Яндекс Доставке
        confirmationTimer: null,      // ID таймера
        confirmationTimeout: 600,     // Таймаут подтверждения (сек)
        timeRemaining: 600,           // Оставшееся время (сек)
        isLocked: false,              // true когда адрес заблокирован
    };

    /* ==================== Reset State ==================== */

    /**
     * Сбрасывает состояние виджета доставки в начальное.
     */
    function resetState() {
        state.selectedType = null;
        state.selectedAddress = '';
        state.selectedCoords = [];
        state.selectedPvzId = '';
        state.selectedPvzName = '';
        state.selectedWorkSchedule = '';
        state.selectedDistance = null;
        state.expressClaimId = '';
        state.estimatedCost = 0;
        state.step = 1;
        state.selectedOfferId = '';
        state.deliveryOrderCreated = false;
        state.confirmationTimer = null;
        state.timeRemaining = CONFIG.CONFIRMATION_TIMEOUT_SECONDS;
        state.isLocked = false;

        // Останавливаем таймер если есть
        stopConfirmationTimer();

        console.log('[YandexDelivery] State reset');
    }

    /* ==================== Config ==================== */
    const CONFIG = {
        CREATE_EXPRESS_URL: '/checkout/create-express-delivery/',
        CANCEL_EXPRESS_URL: '/checkout/cancel-express-delivery/',
        CALCULATE_DELIVERY_URL: '/checkout/calculate-delivery/',
        OFFERS_INFO_URL: '/checkout/offers-info/',
        GEOCODE_URL: '/checkout/geocode-address/',
        PVZ_LOCATIONS_URL: '/checkout/pvz-locations/',
        DEBOUNCE_MS: 600,
        SHOP_LAT: window.YANDEX_SHOP_LAT ?? 53.216940239129094,
        SHOP_LON: window.YANDEX_SHOP_LON ?? 50.162688008923745,
        CONFIRMATION_TIMEOUT_SECONDS: 600, // 10 минут
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

        // Пытаемся найти корзину несколькими способами
        // Способ 1: карточка "Ваш заказ" в правой колонке
        let orderCard = document.querySelector('.col-md-4 .card-body');
        if (!orderCard) {
            // Способ 2: карточка с классом order-summary или similar
            orderCard = document.querySelector('.order-summary, .order-card, .card-body');
        }
        if (!orderCard) {
            // Способ 3: ищем все карточки с товарами
            const allCards = document.querySelectorAll('.card-body');
            if (allCards.length > 0) {
                orderCard = allCards[0];
            }
        }

        if (!orderCard) {
            console.warn('[YandexDelivery] Order card not found, trying alternative selectors');
            // Финальная попытка: ищем строки товаров по всему документу
            const allRows = document.querySelectorAll('.d-flex.justify-content-between');
            if (allRows.length > 0) {
                console.log('[YandexDelivery] Found', allRows.length, 'rows, parsing directly');
                parseCartRows(allRows);
                console.log('[YandexDelivery] Cart loaded from page (direct):', cartState.items);
                return cartState.items;
            }
            console.warn('[YandexDelivery] No order card or rows found');
            return cartState.items;
        }

        // Пропускаем первую строку (итого за товары), берём элементы товаров
        const rows = orderCard.querySelectorAll('.d-flex.justify-content-between');
        if (rows.length === 0) {
            console.warn('[YandexDelivery] No rows found in order card');
            return cartState.items;
        }

        parseCartRows(rows);

        console.log('[YandexDelivery] Cart loaded from page:', cartState.items);
        return cartState.items;
    }

    /**
     * Парсит строки товаров из DOM.
     */
    function parseCartRows(rows) {
        let itemIndex = 0;

        rows.forEach((row) => {
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

    async function getDeliveryOffers(coords, address, deliveryType, pvzId) {
        // Get available delivery intervals via offers/info API
        try {
            if (cartState.items.length === 0) {
                loadCartFromPage();
            }
            if (!cartState.packagesLoaded) {
                await loadPackagesFromAPI();
            }

            const recipient = {
                first_name: $('#id_first_name')?.value || '',
                last_name: $('#id_last_name')?.value || '',
                phone: $('#id_phone')?.value || '',
                email: $('#id_email')?.value || '',
            };

            let parsedCoords = coords;
            if (typeof coords === 'string') {
                parsedCoords = coords.split(',').map(c => parseFloat(c.trim()));
            }

            // Map frontend delivery type to backend values
            const deliveryTypeMap = { courier: 'courier', pvz: 'pickup', postomat: 'postamat' };
            const backendDeliveryType = deliveryTypeMap[deliveryType] || deliveryType || 'courier';

            const payload = {
                destination_coords: parsedCoords,
                destination_address: address,
                pvz_id: pvzId || null,
                delivery_type: backendDeliveryType,
                cart_items: cartState.items.length > 0 ? cartState.items : [],
                recipient: recipient,
            };

            const data = await apiPost(CONFIG.OFFERS_INFO_URL, payload);
            return data;
        } catch (err) {
            console.error('[YandexDelivery] Offers info error:', err);
            return { success: false, error: 'Сетевая ошибка' };
        }
    }

    async function calculateDelivery(coords, address, deliveryType, pvzId) {
        try {
            // Load cart items from DOM if not already loaded
            if (cartState.items.length === 0) {
                loadCartFromPage();
                console.log('[YandexDelivery] Cart items after load:', cartState.items);
            }
            // Load packages from API if not already loaded
            if (!cartState.packagesLoaded) {
                await loadPackagesFromAPI();
            }

            // Если корзина всё ещё пуста, отправляем пустой массив
            // бэкенд использует fallback на session cart
            const cartItemsToSend = cartState.items.length > 0 ? cartState.items : [];

            // Parse coords - ensure it's [lon, lat] format
            let parsedCoords = coords;
            if (typeof coords === 'string') {
                parsedCoords = coords.split(',').map(c => parseFloat(c.trim()));
            }

            // Collect recipient info from checkout form
            const recipient = {
                first_name: $('#id_first_name')?.value || '',
                last_name: $('#id_last_name')?.value || '',
                phone: $('#id_phone')?.value || '',
                email: $('#id_email')?.value || '',
            };

            // Map frontend delivery type to backend values
            const deliveryTypeMap = { courier: 'courier', pvz: 'pickup', postomat: 'postamat' };
            const backendDeliveryType = deliveryTypeMap[deliveryType] || deliveryType || 'courier';

            const payload = {
                destination_coords: parsedCoords,
                destination_address: address,
                pvz_id: pvzId || null,
                delivery_type: backendDeliveryType,
                cart_items: cartItemsToSend,
                recipient: recipient,
            };

            // Логирование данных для отладки расчета доставки
            console.log('[YandexDelivery] === Данные для расчета доставки ===');
            console.log('[YandexDelivery] Тип доставки:', payload.delivery_type);
            console.log('[YandexDelivery] Пункт отправки:');
            if (payload.delivery_type === 'pickup') {
                console.log('[YandexDelivery]   Адрес:', window.YANDEX_PVZ_ADDRESS || 'г. Самара, ул. Лукачева, д. 6');
                console.log('[YandexDelivery]   Координаты:', `[${window.YANDEX_PVZ_LON || 50.150500}, ${window.YANDEX_PVZ_LAT || 53.200850}]`);
                console.log('[YandexDelivery]   ID ПВЗ:', window.YANDEX_PVZ_ID || 'd0222b1e-73ff-4274-9c68-42c79d4c7eae');
            } else {
                console.log('[YandexDelivery]   Адрес:', window.YANDEX_SHOP_ADDRESS || 'Самара, ул. Революционная, д. 3');
                console.log('[YandexDelivery]   Координаты:', `[${window.YANDEX_SHOP_LON || 50.162688008923745}, ${window.YANDEX_SHOP_LAT || 53.216940239129094}]`);
            }
            console.log('[YandexDelivery] Координаты доставки:', payload.destination_coords);
            console.log('[YandexDelivery] Адрес доставки:', payload.destination_address);
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
                return {
                    success: true,
                    price: data.price,
                    delivery_days: data.delivery_days,
                    claim_id: data.claim_id || '',
                };
            }
            return { success: false, error: data.error || 'Не удалось рассчитать стоимость' };
        } catch (err) {
            console.error('[YandexDelivery] Calculate error:', err);
            return { success: false, error: 'Сетевая ошибка' };
        }
    }

    /* ==================== Express Order Creation ==================== */

    /**
     * Обновляет состояние кнопки расчета доставки для курьера.
     * Активирует кнопку если адрес выбран.
     */
    function updateCourierDeliveryButton() {
        const calcBtn = $('#calculateDeliveryBtn');
        const costEl = $('#widgetCost');

        // Активируем кнопку расчета если адрес выбран
        if (state.selectedAddress && state.selectedCoords.length >= 2) {
            if (calcBtn) {
                calcBtn.disabled = false;
                const btnText = state.selectedAddress.length > 30
                    ? state.selectedAddress.substring(0, 30) + '...'
                    : state.selectedAddress;
                YandexDeliveryUtils.setTextContent(
                    calcBtn,
                    `🚚 Рассчитать доставку (${btnText})`
                );
            }
            // Сбрасываем поле цены
            if (costEl) {
                YandexDeliveryUtils.setTextContent(costEl, 'Нажмите «Рассчитать доставку»');
            }
            console.log('[YandexDelivery] Address selected, calculate button activated:', state.selectedAddress);
        } else {
            if (calcBtn) calcBtn.disabled = true;
            console.log('[YandexDelivery] No address selected, calculate button disabled');
        }
    }

    /**
     * Создаёт заказ в Яндекс Доставке по клику на кнопку «Рассчитать доставку».
     * Запускает таймер на 10 минут для подтверждения.
     */
    async function createExpressDelivery(coords, address) {
        const costEl = $('#widgetCost');
        const confirmBtn = $('#confirmDeliveryBtn');
        const cancelBtn = $('#cancelDeliveryBtn');

        console.log('[YandexDelivery] createExpressDelivery:', { coords, address });

        YandexDeliveryUtils.showLoading(costEl);
        if (confirmBtn) confirmBtn.disabled = true;
        if (cancelBtn) cancelBtn.disabled = true;

        // Загружаем корзину
        if (cartState.items.length === 0) {
            loadCartFromPage();
        }
        if (!cartState.packagesLoaded) {
            await loadPackagesFromAPI();
        }

        const cartItemsToSend = cartState.items.length > 0 ? cartState.items : [];

        let parsedCoords = coords;
        if (typeof coords === 'string') {
            parsedCoords = coords.split(',').map(c => parseFloat(c.trim()));
        }

        const payload = {
            destination_coords: parsedCoords,
            destination_address: address,
            delivery_type: 'courier',
            cart_items: cartItemsToSend,
        };

        try {
            console.log('[YandexDelivery] POST', CONFIG.CREATE_EXPRESS_URL, JSON.stringify(payload));
            const result = await apiPost(CONFIG.CREATE_EXPRESS_URL, payload);

            console.log('[YandexDelivery] createExpressDelivery result:', JSON.stringify(result));

            if (result.success && result.price && result.claim_id) {
                console.log('[YandexDelivery] ✓ success, price:', result.price, 'claim_id:', result.claim_id, 'expires:', result.expires_in_seconds);

                // Сохраняем данные
                state.expressClaimId = result.claim_id;
                state.estimatedCost = parseFloat(result.price);
                state.deliveryOrderCreated = true;
                state.timeRemaining = CONFIG.CONFIRMATION_TIMEOUT_SECONDS;

                console.log('[YandexDelivery] State updated:', {
                    expressClaimId: state.expressClaimId,
                    estimatedCost: state.estimatedCost,
                    deliveryOrderCreated: state.deliveryOrderCreated,
                    timeRemaining: state.timeRemaining
                });

                // Обновляем UI
                const formattedPrice = YandexDeliveryUtils.formatPrice(result.price);
                const formattedTime = formatTime(result.expires_in_seconds);
                console.log('[YandexDelivery] UI: setting costEl to:', formattedPrice + ' ₽ • ' + formattedTime);
                YandexDeliveryUtils.setTextContent(
                    costEl,
                    formattedPrice + ' ₽ • ' + formattedTime
                );
                console.log('[YandexDelivery] costEl textContent:', costEl ? costEl.textContent : 'NULL');

                // Показываем кнопки подтверждения/отмены
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    console.log('[YandexDelivery] confirmBtn enabled');
                }
                if (cancelBtn) {
                    cancelBtn.disabled = false;
                    console.log('[YandexDelivery] cancelBtn enabled');
                }

                // Показываем блок с деталями расчета (где находится widgetCost)
                const calcDetailsBlock = $('#calcDetailsBlock');
                if (calcDetailsBlock) {
                    show(calcDetailsBlock);
                    // Заполняем детали расчета
                    showCalcDetails();
                    console.log('[YandexDelivery] Showed calcDetailsBlock and filled data');
                }

                // Запускаем таймер
                startConfirmationTimer();

                // Блокируем изменение адреса
                lockAddress();

                console.log('[YandexDelivery] ✓ Order created successfully, timer started');
            } else {
                const errorMsg = result.error || 'Не удалось создать заказ';
                console.error('[YandexDelivery] ✗ Failed:', result);
                YandexDeliveryUtils.setTextContent(costEl, errorMsg);
                if (confirmBtn) confirmBtn.disabled = true;
                if (cancelBtn) cancelBtn.disabled = true;
                console.error('[YandexDelivery] Failed to create order:', errorMsg);
            }
        } catch (err) {
            console.error('[YandexDelivery] createExpressDelivery error:', err);
            YandexDeliveryUtils.setTextContent(costEl, 'Сетевая ошибка');
            if (confirmBtn) confirmBtn.disabled = true;
            if (cancelBtn) cancelBtn.disabled = true;
        }
    }

    /**
     * Форматирует время из секунд в ММ:СС
     */
    function formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    /**
     * Запускает 10-минутный таймер подтверждения заказа
     */
    function startConfirmationTimer() {
        // Очищаем предыдущий таймер если есть
        stopConfirmationTimer();

        const timerEl = $('#deliveryTimer');
        const orderTimerText = $('#orderDeliveryTimerText');
        const costEl = $('#widgetCost');
        const confirmBtn = $('#confirmDeliveryBtn');
        const cancelBtn = $('#cancelDeliveryBtn');

        state.confirmationTimer = setInterval(() => {
            state.timeRemaining--;

            // Обновляем отображение таймера в модалке
            if (timerEl) {
                timerEl.textContent = formatTime(state.timeRemaining);
            }

            // Обновляем отображение таймера на странице оформления
            if (orderTimerText) {
                orderTimerText.textContent = formatTime(state.timeRemaining);
            }

            // Обновляем цену с таймером
            if (costEl && state.deliveryOrderCreated) {
                YandexDeliveryUtils.setTextContent(
                    costEl,
                    `${YandexDeliveryUtils.formatPrice(state.estimatedCost)} ₽ • ${formatTime(state.timeRemaining)}`
                );
            }

            // Время вышло — автоматически отменяем
            if (state.timeRemaining <= 0) {
                stopConfirmationTimer();
                if (costEl) YandexDeliveryUtils.setTextContent(costEl, 'Время подтверждения истекло');
                if (confirmBtn) confirmBtn.disabled = true;
                if (cancelBtn) cancelBtn.disabled = true;
                console.warn('[YandexDelivery] Confirmation timer expired');
            }
        }, 1000);

        console.log('[YandexDelivery] Timer started:', CONFIG.CONFIRMATION_TIMEOUT_SECONDS, 'seconds');
    }

    /**
     * Останавливает таймер подтверждения
     */
    function stopConfirmationTimer() {
        if (state.confirmationTimer) {
            clearInterval(state.confirmationTimer);
            state.confirmationTimer = null;
            console.log('[YandexDelivery] Timer stopped');
        }
    }

    /**
     * Отменяет заказ в Яндекс Доставке
     */
    async function cancelDelivery() {
        const costEl = $('#widgetCost');
        const confirmBtn = $('#confirmDeliveryBtn');
        const cancelBtn = $('#cancelDeliveryBtn');

        console.log('[YandexDelivery] Cancelling delivery:', state.expressClaimId);

        stopConfirmationTimer();

        try {
            const result = await apiPost(CONFIG.CANCEL_EXPRESS_URL, {
                claim_id: state.expressClaimId,
            });

            console.log('[YandexDelivery] Cancel result:', result);
        } catch (err) {
            console.error('[YandexDelivery] Cancel error:', err);
            // Даже если отмена не удалась — всё равно разблокируем
        }

        // Сбрасываем состояние
        resetDeliveryState();

        // Показываем сообщение
        YandexDeliveryUtils.setTextContent(costEl, 'Заказ отменён');
        if (confirmBtn) confirmBtn.disabled = true;
        if (cancelBtn) cancelBtn.disabled = true;
    }

    /**
     * Сбрасывает состояние доставки в исходное
     */
    function resetDeliveryState() {
        state.deliveryOrderCreated = false;
        state.expressClaimId = '';
        state.estimatedCost = 0;
        state.timeRemaining = CONFIG.CONFIRMATION_TIMEOUT_SECONDS;
        state.isLocked = false;

        stopConfirmationTimer();
        unlockAddress();
    }

    /**
     * Блокирует карту и поле ввода адреса
     */
    function lockAddress() {
        state.isLocked = true;

        const addressInput = $('#yandexAddressInput');
        const mapContainer = $('#yandexDeliveryWidgetContainer');
        const confirmBtn = $('#confirmDeliveryBtn');
        const cancelBtn = $('#cancelDeliveryBtn');

        if (addressInput) {
            addressInput.disabled = true;
            addressInput.classList.add('bg-light');
        }

        if (mapContainer) {
            mapContainer.classList.add('opacity-50', 'pointer-events-none');
        }

        // Добавляем сообщение о блокировке
        const warningEl = $('#addressLockedWarning');
        if (warningEl) {
            show(warningEl);
        }

        console.log('[YandexDelivery] Address locked');
    }

    /**
     * Разблокирует карту и поле ввода адреса
     */
    function unlockAddress() {
        state.isLocked = false;

        const addressInput = $('#yandexAddressInput');
        const mapContainer = $('#yandexDeliveryWidgetContainer');
        const warningEl = $('#addressLockedWarning');

        if (addressInput) {
            addressInput.disabled = false;
            addressInput.classList.remove('bg-light');
        }

        if (mapContainer) {
            mapContainer.classList.remove('opacity-50', 'pointer-events-none');
        }

        if (warningEl) {
            hide(warningEl);
        }

        console.log('[YandexDelivery] Address unlocked');
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

            console.log('[YandexDelivery] API response for type', type + ':', JSON.stringify(data).substring(0, 200));

            if (!data.success) {
                console.error('[YandexDelivery] API error for type', type + ':', data.error);
                return { success: false, error: data.error || 'Ошибка API' };
            }

            if (!data.points?.length) {
                console.warn('[YandexDelivery] No points loaded for type:', type, 'message:', data.message);
                return { success: false, error: data.message || 'Точки доставки недоступны' };
            }

            console.log('[YandexDelivery] Points loaded for type', type + ':', data.points.length);
            return { success: true, points: data.points };
        } catch (err) {
            console.error('[YandexDelivery] Load PVZ error:', err);
            return { success: false, error: 'Сетевая ошибка: ' + err.message };
        }
    }

    /* ==================== DOM Helpers ==================== */
    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => document.querySelectorAll(selector);
    const show = (el) => el?.classList.remove('d-none');
    const hide = (el) => el?.classList.add('d-none');

    /**
     * Обновляет текст подсказки под картой в зависимости от типа доставки.
     */
    function updateMapHintText() {
        const hintEl = $('#mapHintText');
        if (!hintEl) return;

        const hints = {
            courier: '🗺️ Нажмите на карту в месте доставки или введите адрес в строку поиска',
            pvz: '📦 Выберите пункт выдачи на карте',
            postomat: '📮 Выберите постомат на карте',
        };
        hintEl.textContent = hints[state.selectedType] || hints.courier;
    }

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
                // Сбрасываем выбранный пункт при смене типа доставки,
                // чтобы старая цена и pvz_id не передавались на бэкенд
                state.selectedType = e.target.value;
                state.selectedPvzId = '';
                state.selectedPvzName = '';
                state.selectedAddress = '';
                state.selectedCoords = [];
                state.estimatedCost = 0;
                updateMapHintText();
                goToStep(2);
                updateConfirmButton();
            }
        });

        // Автокомплит
        initAutocomplete();

        // Подтверждение
        $('#confirmDeliveryBtn')?.addEventListener('click', handleConfirm);

        // Отмена заказа доставки
        $('#cancelDeliveryBtn')?.addEventListener('click', () => {
            if (state.deliveryOrderCreated) {
                if (confirm('Отменить созданный заказ в Яндекс Доставке?')) {
                    cancelDelivery();
                }
            }
        });

        // Расчет доставки (для курьера)
        $('#calculateDeliveryBtn')?.addEventListener('click', () => {
            if (state.selectedType === 'courier' && state.selectedAddress && state.selectedCoords.length >= 2) {
                if (state.deliveryOrderCreated) {
                    // Заказ уже создан — просто подтверждаем
                    handleConfirm();
                } else {
                    // Создаем новый заказ
                    createExpressDelivery(
                        state.selectedCoords.join(','),
                        state.selectedAddress
                    );
                }
            }
        });

        // Кнопка открытия
        $('#openDeliveryModal')?.addEventListener('click', (e) => {
            e.preventDefault();
            // Validate recipient fields before opening modal
            const firstName = $('#id_first_name')?.value?.trim() || '';
            const lastName = $('#id_last_name')?.value?.trim() || '';
            const phone = $('#id_phone')?.value?.trim() || '';
            const email = $('#id_email')?.value?.trim() || '';

            if (!firstName || !lastName || !phone || !email) {
                alert('Пожалуйста, заполните контактные данные (имя, фамилия, телефон, email) перед выбором доставки.');
                // Focus the first empty field
                if (!firstName) $('#id_first_name')?.focus();
                else if (!lastName) $('#id_last_name')?.focus();
                else if (!phone) $('#id_phone')?.focus();
                else if (!email) $('#id_email')?.focus();
                return;
            }

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
        const widgetContainer = $('#yandexDeliveryWidgetContainer');
        const courierSearchWrap = $('#courierSearchWrap');
        const mapWarning = $('#mapUnavailableWarning');

        hide(step1);
        hide(step2);

        if (stepNumber === 1) {
            show(step1);
        } else if (stepNumber === 2) {
            show(step2);
            if (state.selectedType === 'courier') {
                // Показываем блок с полем ввода адреса и кнопкой расчета
                show(courierSearchWrap);
                hide(mapWarning);
                hide($('#selectedPvzInfo'));
                hide($('#calcDetailsBlock'));
                hide($('#courierCostBlock'));
                show(widgetContainer);
                updateMapHintText();
                loadYmaps();
            } else {
                hide(courierSearchWrap);
                hide(mapWarning);
                show(widgetContainer);
                hide($('#selectedPvzInfo'));
                hide($('#calcDetailsBlock'));
                // Очищаем стоимость доставки — она будет пересчитана при выборе пункта
                const costEl = $('#widgetCost');
                if (costEl) costEl.textContent = 'Расчёт...';
                updateMapHintText();
                loadYmaps();
            }
        }
    }

    /**
     * Показывает блок с деталями расчета под картой.
     */
    function showCalcDetails() {
        const calcDetailsBlock = $('#calcDetailsBlock');
        if (!calcDetailsBlock) return;

        // Заполняем детали расчета
        const calcAddress = $('#calcAddress');
        const calcPvzBlock = $('#calcPvzBlock');
        const calcPvzName = $('#calcPvzName');
        const calcDeliveryType = $('#calcDeliveryType');
        const calcItemDetails = $('#calcItemDetails');
        const calcPostomatInfo = $('#calcPostomatInfo');

        if (calcAddress) calcAddress.textContent = state.selectedAddress;

        if (calcDeliveryType) {
            const typeLabels = {
                courier: '🚗 Курьер',
                pvz: '📦 Пункт выдачи (ПВЗ)',
                postomat: '📮 Постомат',
            };
            calcDeliveryType.textContent = typeLabels[state.selectedType] || '🚗 Курьер';
        }

        if (calcItemDetails) {
            if (cartState.packagesLoaded) {
                const summary = getCartSummary();
                calcItemDetails.textContent = `${summary.totalItems} шт, ${summary.totalWeight} г`;
            } else {
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

        // Отображаем доп. информацию о постомате (график работы, расстояние)
        if (state.selectedType === 'postomat' && calcPostomatInfo) {
            const scheduleText = state.selectedWorkSchedule || '';
            const distanceText = state.selectedDistance ? `${state.selectedDistance} от магазина` : '';
            let infoHtml = '';
            if (scheduleText) {
                infoHtml += `<div>🕐 ${YandexDeliveryUtils.escapeHtml(scheduleText)}</div>`;
            }
            if (distanceText) {
                infoHtml += `<div>📏 ${YandexDeliveryUtils.escapeHtml(distanceText)}</div>`;
            }
            calcPostomatInfo.innerHTML = infoHtml;
            show(calcPostomatInfo);
        } else if (calcPostomatInfo) {
            hide(calcPostomatInfo);
        }

        show(calcDetailsBlock);
    }

    function resetState() {
        state.selectedType = null;
        state.selectedAddress = '';
        state.selectedCoords = [];
        state.selectedPvzId = '';
        state.selectedPvzName = '';
        state.selectedWorkSchedule = '';
        state.selectedDistance = null;
        state.selectedOfferId = '';
        state.expressClaimId = '';
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

        const courierSearchWrap = $('#courierSearchWrap');
        if (courierSearchWrap) hide(courierSearchWrap);

        const courierCostBlock = $('#courierCostBlock');
        if (courierCostBlock) hide(courierCostBlock);

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

        // Устанавливаем координаты из автокомплита
        if (feature.coords) {
            state.selectedCoords = feature.coords;
        }

        // Если заказ уже создан — сбрасываем состояние при изменении адреса
        if (state.deliveryOrderCreated && state.selectedType === 'courier') {
            console.log('[YandexDelivery] Address changed, resetting delivery order state');
            stopConfirmationTimer();
            resetDeliveryState();
        }

        // Для курьера — обновляем метку на карте и активируем кнопку расчета
        // Для ПВЗ/постомат — рассчитываем доставку как раньше
        if (state.selectedType === 'courier') {
            const coords = feature.coords || state.selectedCoords;
            if (coords && coords.length >= 2) {
                // Просто обновляем метку и активируем кнопку расчета
                updateCourierDeliveryButton();
            }
        } else {
            // Для ПВЗ/постомат геокодируем адрес
            geocodeAndCalculate(feature.text, feature.coords);
        }
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
        if (state.selectedType === 'courier') {
            // Для курьера показываем стоимость в widgetCost
            YandexDeliveryUtils.setTextContent(costEl, `${YandexDeliveryUtils.formatPrice(calc.price)} ₽`);
            YandexDeliveryUtils.setTextContent(etaEl, calc.delivery_days ? `(${calc.delivery_days} дн.)` : '');
            YandexDeliveryUtils.setTextContent(etaLabelEl, calc.delivery_days ? ` ETA: ${calc.delivery_days} дн.` : ' ETA: ');
        } else {
            YandexDeliveryUtils.setTextContent(costEl, `${YandexDeliveryUtils.formatPrice(calc.price)} ₽`);
            YandexDeliveryUtils.setTextContent(etaEl, calc.delivery_days ? `(${calc.delivery_days} дн.)` : '');
            YandexDeliveryUtils.setTextContent(etaLabelEl, calc.delivery_days ? ` ETA: ${calc.delivery_days} дн.` : ' ETA: ');

            // Показываем детали расчета под картой
            showCalcDetails();
        }
        updateConfirmButton();
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
        // Для курьера — заказ должен быть создан через кнопку «Рассчитать доставку»
        if (state.selectedType === 'courier') {
            if (!state.deliveryOrderCreated) {
                showError('Сначала нажмите «Рассчитать доставку» для создания заказа в Яндекс Доставке');
                return;
            }

            clearError();

            YandexDeliveryUtils.setFieldValue('id_delivery_address', state.selectedAddress);
            YandexDeliveryUtils.setFieldValue('id_delivery_type', 'courier');
            YandexDeliveryUtils.setFieldValue('id_yandex_station_id', state.selectedPvzId);
            YandexDeliveryUtils.setFieldValue('id_yandex_station_name', state.selectedPvzName || state.selectedAddress);
            YandexDeliveryUtils.setFieldValue('id_yandex_delivery_cost', state.estimatedCost);
            if (state.expressClaimId) {
                YandexDeliveryUtils.setFieldValue('id_express_claim_id', state.expressClaimId);
            }

            const checkoutAddr = $('#id_delivery_address');
            if (checkoutAddr) checkoutAddr.value = state.selectedAddress;

            updateDeliverySummary();
            updateOrderDeliveryLocation();

            // Показываем таймер на странице оформления заказа
            const orderTimerBlock = $('#orderDeliveryTimer');
            if (orderTimerBlock) {
                YandexDeliveryUtils.showElement(orderTimerBlock);
            }

            // Разблокируем адрес и закрываем модалку
            // ВАЖНО: НЕ вызываем stopConfirmationTimer() — таймер уже запущен и
            // startConfirmationTimer() обновляет #orderDeliveryTimerText каждую секунду
            unlockAddress();
            closeModal();
            return;
        }

        // Для ПВЗ/постомат — старый расчёт
        const errors = [];
        if (!state.selectedPvzId) errors.push('Выберите пункт выдачи или постомат');
        if (!state.selectedCoords.length) errors.push('Координаты не получены');
        if (!state.selectedAddress) errors.push('Введите адрес доставки');
        if (state.estimatedCost <= 0) errors.push('Не удалось рассчитать стоимость');

        if (errors.length) {
            showError(errors.join(' '));
            return;
        }

        clearError();

        // Map frontend type to backend Order.DeliveryType values
        // 'postomat' (frontend) -> 'postamat' (backend model)
        const deliveryTypeMap = { courier: 'courier', pvz: 'pickup', postomat: 'postamat' };
        const backendDeliveryType = deliveryTypeMap[state.selectedType] || state.selectedType;

        YandexDeliveryUtils.setFieldValue('id_delivery_address', state.selectedAddress);
        YandexDeliveryUtils.setFieldValue('id_delivery_type', backendDeliveryType);
        YandexDeliveryUtils.setFieldValue('id_yandex_station_id', state.selectedPvzId);
        YandexDeliveryUtils.setFieldValue('id_yandex_station_name', state.selectedPvzName || state.selectedAddress);
        YandexDeliveryUtils.setFieldValue('id_yandex_delivery_cost', state.estimatedCost);
        // Сохраняем selected offer_id для Other Day API
        if (state.selectedOfferId) {
            YandexDeliveryUtils.setFieldValue('id_yandex_offer_id', state.selectedOfferId);
        }
        // Сохраняем delivery_date/delivery_time если заказ создан через request/create
        if (state.deliveryDate) {
            YandexDeliveryUtils.setFieldValue('id_delivery_date', state.deliveryDate);
        }
        if (state.deliveryTime) {
            YandexDeliveryUtils.setFieldValue('id_delivery_time', state.deliveryTime);
        }
        if (state.deliveryRequest_id) {
            YandexDeliveryUtils.setFieldValue('id_yandex_request_id', state.deliveryRequest_id);
        }

        const checkoutAddr = $('#id_delivery_address');
        if (checkoutAddr) checkoutAddr.value = state.selectedAddress;

        updateDeliverySummary();
        updateOrderDeliveryLocation();
        closeModal();
    }

    /* ==================== Order Delivery Location ==================== */
    function updateOrderDeliveryLocation() {
        const locationBlock = $('#orderDeliveryLocation');
        const locationText = $('#orderDeliveryLocationText');
        if (!locationBlock || !locationText) return;

        if (!state.selectedPvzName) {
            hide(locationBlock);
            return;
        }

        const typeLabels = {
            pvz: '📦 ПВЗ',
            postomat: '📮 Постомат',
        };
        const typeLabel = typeLabels[state.selectedType] || '';

        locationText.innerHTML = `
            <div><strong>${typeLabel}:</strong> ${YandexDeliveryUtils.escapeHtml(state.selectedPvzName)}</div>
            <div class="mt-1"><strong>Адрес:</strong> ${YandexDeliveryUtils.escapeHtml(state.selectedAddress)}</div>
        `;

        show(locationBlock);
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
        if (!btn) return;

        // Для курьера кнопка активна только если заказ создан
        if (state.selectedType === 'courier') {
            btn.disabled = !state.deliveryOrderCreated;
            console.log('[YandexDelivery] updateConfirmButton (courier):', {
                deliveryOrderCreated: state.deliveryOrderCreated,
                canConfirm: state.deliveryOrderCreated
            });
        } else {
            // Для ПВЗ/постомат — старый расчёт
            const canConfirm = state.selectedType && state.estimatedCost > 0;
            btn.disabled = !canConfirm;
            console.log('[YandexDelivery] updateConfirmButton (PVZ):', {
                selectedType: state.selectedType,
                estimatedCost: state.estimatedCost,
                canConfirm: canConfirm
            });
        }
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

            // Загружаем ПВЗ/постоматы только для этих типов доставки
            // Для курьера пользователь выбирает адрес кликом по карте
            if (state.selectedType === 'pvz' || state.selectedType === 'postomat') {
                loadPvzOnMap();
            }

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

        // Для ПВЗ и постоматов клик по карте должен показывать подсказку
        if (state.selectedType === 'pvz' || state.selectedType === 'postomat') {
            showPointSelectionHint();
            return;
        }

        // Для курьерской доставки — реверс-геокодирование
        showCourierMapLoading();
        ymaps.geocode(coords.join(',')).then((res) => {
            const first = res.geoObjects.get(0);
            if (!first) {
                hideCourierMapLoading();
                showMapError('Не удалось определить адрес по координатам');
                return;
            }
            const address = first.properties.get('fullName') || first.properties.get('text');
            hideCourierMapLoading();
            onReverseGeocode(address, coords);
        }).catch((err) => {
            console.error('[YandexDelivery] Reverse geocode error:', err);
            hideCourierMapLoading();
            showMapError('Ошибка при определении адреса');
        });
    }

    function onReverseGeocode(address, coords) {
        if (state.selectedPlacemark && state.mapInstance) {
            state.mapInstance.geoObjects.remove(state.selectedPlacemark);
        }

        state.selectedPlacemark = new ymaps.Placemark(coords, {
            hintContent: address,
            balloonContent: '✅ Этот адрес подходит? Нажмите «Рассчитать доставку»',
        }, { preset: 'islands#orangeCircleDotIcon' });
        state.mapInstance.geoObjects.add(state.selectedPlacemark);

        // Вставляем адрес в строку поиска
        const addressInput = $('#yandexAddressInput');
        if (addressInput) {
            addressInput.value = address;
        }

        state.selectedCoords = coords;
        state.selectedAddress = address;

        // Если заказ уже создан — сбрасываем состояние при изменении адреса
        if (state.deliveryOrderCreated && state.selectedType === 'courier') {
            console.log('[YandexDelivery] Address changed via map click, resetting');
            stopConfirmationTimer();
            resetDeliveryState();
        }

        // Обновляем метку на карте и активируем кнопку расчета
        updateCourierDeliveryButton();
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
            const errorMsg = data.error || `${pointLabel} временно недоступны`;
            showMapError(errorMsg);
            return;
        }

        console.log('[YandexDelivery] Loaded', data.points.length, pointLabel);

        state.pvzPlacemarks = [];

        data.points.forEach((point) => {
            if (!point.latitude || !point.longitude) return;

            // Формируем полное описание для балуна
            let balloonContent = `<strong>${YandexDeliveryUtils.escapeHtml(point.name)}</strong><br>`;
            balloonContent += `${YandexDeliveryUtils.escapeHtml(point.address)}`;

            // Добавляем информацию о расстоянии
            if (point.distance_km != null) {
                balloonContent += `<br>📏 ${point.distance_km} км от магазина`;
            }

            // Добавляем график работы для постоматов
            if (state.selectedType === 'postomat' && point.work_schedule) {
                const scheduleText = formatWorkSchedule(point.work_schedule);
                if (scheduleText) {
                    balloonContent += `<br>🕐 ${YandexDeliveryUtils.escapeHtml(scheduleText)}`;
                }
            }

            const placemark = new ymaps.Placemark([point.latitude, point.longitude], {
                hintContent: point.name,
                balloonContent: balloonContent,
            }, { preset: state.selectedType === 'postomat' ? 'islands#redShoppingIcon' : 'islands#darkGreenShoppingIcon' });

            placemark.events.add('click', () => {
                try {
                    console.log('[YandexDelivery] Point clicked:', point.name);
                    // Используем полное описание адреса
                    const pointLabelFull = point.name + (point.address ? ' — ' + point.address : '');
                    handlePointSelected({
                        id: point.id,
                        name: point.name,
                        address: point.address || pointLabelFull,
                        fullAddress: pointLabelFull,
                        coordinates: [point.longitude, point.latitude],
                        work_schedule: point.work_schedule || {},
                        distance_km: point.distance_km,
                    });
                } catch (err) {
                    console.error('[YandexDelivery] Point click error:', err);
                    // Показываем подсказку вместо ошибки
                    showPointSelectionHint();
                }
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

    /**
     * Показывает индикатор загрузки на карте при геокодировании (курьер).
     */
    function showCourierMapLoading() {
        const costEl = $('#widgetCost');
        if (costEl) {
            costEl.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Определение адреса...';
            costEl.classList.add('border-info');
        }
    }

    /**
     * Убирает индикатор загрузки на карте.
     */
    function hideCourierMapLoading() {
        const costEl = $('#widgetCost');
        if (costEl) {
            costEl.classList.remove('border-info');
        }
    }

    /**
     * Показывает блок с рассчитанной стоимостью доставки для курьера.
     */
    function showCourierDeliveryCost(calc) {
        const block = $('#courierCostBlock');
        if (!block) return;

        const addressEl = $('#courierCostAddress');
        const priceEl = $('#courierCostPrice');
        const etaEl = $('#courierCostEta');
        const totalEl = $('#courierTotalPrice');

        if (addressEl) addressEl.textContent = state.selectedAddress;
        if (priceEl) priceEl.textContent = `${YandexDeliveryUtils.formatPrice(calc.price)} ₽`;
        if (etaEl) etaEl.textContent = calc.delivery_days ? `(${calc.delivery_days} дн.)` : '';

        // Рассчитываем итоговую сумму — корректно парсим русское форматирование
        const goodsText = $('#orderGoodsTotal')?.textContent || '0';
        // Удаляем пробелы (разделители тысяч), запятую заменяем на точку
        const cleanText = goodsText.replace(/\s/g, '').replace(/,/g, '.');
        const goodsTotal = parseFloat(cleanText) || 0;
        // Гарантируем что price — число (API может вернуть строку)
        const deliveryPrice = typeof calc.price === 'string' ? parseFloat(calc.price.replace(/,/g, '.')) : calc.price;
        const total = goodsTotal + (deliveryPrice || 0);
        if (totalEl) totalEl.textContent = `${YandexDeliveryUtils.formatPrice(total)} ₽`;

        show(block);
    }

    /**
     * Показывает подсказку о необходимости выбрать ПВЗ/постомат на карте.
     */
    function showPointSelectionHint() {
        const hintMessage = state.selectedType === 'postomat'
            ? '📮 Выберите постомат на карте'
            : '📦 Выберите ПВЗ на карте';

        const costEl = $('#widgetCost');
        if (costEl) {
            costEl.innerHTML = `<span class="text-info">${hintMessage}</span>`;
            costEl.classList.add('border-info');

            // Убираем подсказку через 3 секунды, НЕ восстанавливая старую цену
            setTimeout(() => {
                costEl.textContent = 'Расчёт...';
                costEl.classList.remove('border-info');
            }, 3000);
        }

        console.log('[YandexDelivery] Hint:', hintMessage);
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

        // Extract work schedule for postamats
        if (state.selectedType === 'postomat') {
            const schedule = point.work_schedule || {};
            state.selectedWorkSchedule = formatWorkSchedule(schedule);
            state.selectedDistance = point.distance_km ? `${point.distance_km} км` : '';
        }

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

        // Показываем блок с информацией о выбранном ПВЗ/постомате
        if (pvzNameEl) {
            pvzNameEl.textContent = state.selectedAddress;
        }

        // Показываем блок с информацией о выбранном пункте
        if (pvzInfoBlock && state.selectedPvzName) {
            pvzNameEl.textContent = state.selectedAddress;
            YandexDeliveryUtils.showElement(pvzInfoBlock);
        }

        // Запускаем расчет стоимости доставки
        calculateDeliveryCost(state.selectedCoords.join(','), state.selectedAddress);
    }

    /**
     * Форматирует график работы постомата.
     */
    function formatWorkSchedule(schedule) {
        if (!schedule) return '';

        // Handle different schedule formats from Yandex API
        const days = schedule.days || schedule.schedules || [];
        if (Array.isArray(days) && days.length > 0) {
            return days.map(d => {
                const dayName = d.day_name || d.name || '';
                const timeRange = d.time_range || d.hours || '';
                if (dayName && timeRange) return `${dayName}: ${timeRange}`;
                if (dayName) return dayName;
                if (timeRange) return timeRange;
                return '';
            }).filter(Boolean).join('; ');
        }

        // Fallback: try to read from raw schedule object
        if (schedule.monday) return 'Пн: ' + schedule.monday;
        if (schedule.tuesday) return 'Вт: ' + schedule.tuesday;
        if (schedule.daily) return schedule.daily;
        if (schedule.text) return schedule.text;
        if (schedule.description) return schedule.description;

        return '';
    }

    /**
     * Отображает доступные интервалы доставки для ПВЗ/Постомат.
     */
    function renderDeliveryOffers(offers) {
        console.log('[YandexDelivery] renderDeliveryOffers called with:', offers);
        const container = $('#deliveryOffersContainer');
        if (!container) {
            console.error('[YandexDelivery] renderDeliveryOffers: container #deliveryOffersContainer not found');
            return;
        }

        if (!offers || offers.length === 0) {
            console.warn('[YandexDelivery] renderDeliveryOffers: no offers to display');
            hide(container);
            return;
        }

        const listEl = container.querySelector('.offers-list');
        if (!listEl) {
            console.error('[YandexDelivery] renderDeliveryOffers: .offers-list not found');
            return;
        }

        let html = '';
        offers.forEach((offer, index) => {
            console.log(`[YandexDelivery] Offer ${index}:`, offer);
            const isSelected = index === 0 ? ' selected border-primary' : '';
            html += `
                <div class="list-group-item list-group-item-action${isSelected} delivery-offer-item" 
                     data-offer-index="${index}" data-offer-id="${offer.offer_id || ''}">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${offer.formatted_interval || '\u2014'}</strong>
                            ${offer.formatted_date ? `<br><small class="text-muted">${offer.formatted_date}</small>` : ''}
                        </div>
                        <div class="text-end">
                            <div class="fw-bold text-success">${offer.formatted_price || '\u2014'}</div>
                        </div>
                    </div>
                </div>
            `;
        });

        listEl.innerHTML = html;
        show(container);
        hide($('#deliveryErrorBlock'));

        console.log('[YandexDelivery] renderDeliveryOffers: rendered', offers.length, 'offers');

        // Add click handlers
        container.querySelectorAll('.delivery-offer-item').forEach(item => {
            item.addEventListener('click', () => {
                container.querySelectorAll('.delivery-offer-item').forEach(i => {
                    i.classList.remove('selected', 'border-primary');
                });
                item.classList.add('selected', 'border-primary');
                const idx = parseInt(item.dataset.offerIndex);
                const offer = offers[idx];
                state.estimatedCost = parseFloat(offer.price);
                state.selectedOfferId = offer.offer_id || '';
                const costEl = $('#widgetCost');
                if (costEl) {
                    YandexDeliveryUtils.setTextContent(costEl, offer.formatted_price || `${offer.price} \u20bd`);
                }
                updateConfirmButton();
            });
        });
    }

    async function calculateDeliveryCost(coords, address) {
        const costEl = $('#widgetCost');
        const etaEl = $('#widgetEta');
        const etaLabelEl = $('#widgetEtaLabel');
        const confirmBtn = $('#confirmDeliveryBtn');

        console.log('[YandexDelivery] calculateDeliveryCost called:', { coords, address, deliveryType: state.selectedType });

        YandexDeliveryUtils.showLoading(costEl);
        if (confirmBtn) confirmBtn.disabled = true;

        let calc;

        console.log('[YandexDelivery] calculateDeliveryCost: selectedType=', state.selectedType, 'selectedPvzId=', state.selectedPvzId);

        if (state.selectedType === 'pvz' || state.selectedType === 'postomat') {
            // Для ПВЗ/Постомат используем offers/info для получения интервалов
            console.log('[YandexDelivery] Getting offers/info for PVZ/postamat');
            const offersData = await getDeliveryOffers(coords, address, state.selectedType, state.selectedPvzId);

            console.log('[YandexDelivery] offers/info result:', offersData);

            // Проверяем, создан ли заказ сразу (нет доступных интервалов)
            if (offersData.created) {
                console.log('[YandexDelivery] Order created via request/create:', offersData);

                state.estimatedCost = parseFloat(offersData.price) || 0;
                state.deliveryDate = offersData.delivery_date || '';
                state.deliveryTime = offersData.delivery_time || '';
                state.deliveryRequest_id = offersData.request_id || '';
                state.deliveryStatus = offersData.status || '';

                // Форматируем цену
                const formattedPrice = YandexDeliveryUtils.formatPrice(state.estimatedCost);
                const deliveryInfo = state.deliveryTime
                    ? `${formattedPrice} ₽ • ${state.deliveryDate} ${state.deliveryTime}`
                    : `${formattedPrice} ₽ • ${state.deliveryDate || 'ближайшее время'}`;

                YandexDeliveryUtils.setTextContent(costEl, deliveryInfo);

                // Показываем информацию о выбранном ПВЗ/постомате
                const pvzInfo = $('#selectedPvzInfo');
                const pvzNameEl = $('#selectedPvzNameDisplay');
                if (pvzInfo && pvzNameEl && state.selectedPvzName) {
                    pvzNameEl.textContent = state.selectedAddress;
                    show(pvzInfo);
                }

                // Показываем детали расчета под картой
                showCalcDetails();

                // Активируем кнопку подтверждения
                updateConfirmButton();

                // Затемняем карту
                setMapOverlay(true);
                hide($('#deliveryErrorBlock'));
                hide($('#deliveryOffersContainer'));
                return;
            }

            if (offersData.success && offersData.offers?.length) {
                // Показываем интервалы
                renderDeliveryOffers(offersData.offers);
                hide($('#deliveryErrorBlock'));

                // Используем первый оффер для стоимости
                state.estimatedCost = parseFloat(offersData.offers[0].price);
                state.selectedOfferId = offersData.offers[0].offer_id || '';

                YandexDeliveryUtils.setTextContent(costEl, offersData.offers[0].formatted_price || `${YandexDeliveryUtils.formatPrice(state.estimatedCost)} ₽`);

                // Показываем информацию о выбранном ПВЗ/постомате
                const pvzInfo = $('#selectedPvzInfo');
                const pvzNameEl = $('#selectedPvzNameDisplay');
                if (pvzInfo && pvzNameEl && state.selectedPvzName) {
                    pvzNameEl.textContent = state.selectedAddress;
                    show(pvzInfo);
                }

                // Показываем детали расчета под картой
                showCalcDetails();

                // Активируем кнопку подтверждения
                updateConfirmButton();

                // Затемняем карту
                setMapOverlay(true);
            } else {
                // Показываем ошибку если offers/info вернул ошибку
                const errorBlock = $('#deliveryErrorBlock');
                const offersContainer = $('#deliveryOffersContainer');
                if (offersData.error) {
                    console.error('[YandexDelivery] offers/info error:', offersData.error);
                    YandexDeliveryUtils.setTextContent(costEl, `❌ ${offersData.error}`);
                    if (errorBlock) {
                        errorBlock.textContent = `Ошибка получения интервалов: ${offersData.error}`;
                        show(errorBlock);
                    }
                    if (offersContainer) hide(offersContainer);
                    // Затемняем карту при ошибке
                    setMapOverlay(true);
                }
                // Fallback к старому расчету
                console.warn('[YandexDelivery] offers/info failed, falling back to calculateDelivery');
                console.warn('[YandexDelivery] offers/info response:', offersData);
                calc = await calculateDelivery(coords, address, state.selectedType, state.selectedPvzId);
                if (calc.success && calc.price != null && parseFloat(calc.price) > 0) {
                    state.estimatedCost = parseFloat(calc.price);
                    YandexDeliveryUtils.setTextContent(costEl, `${YandexDeliveryUtils.formatPrice(calc.price)} ₽`);
                    if (errorBlock) hide(errorBlock);
                    if (offersContainer) hide(offersContainer);
                    showCalcDetails();
                    updateConfirmButton();
                    // Убираем затемнение при успешном расчёте
                    setMapOverlay(false);
                } else {
                    console.error('[YandexDelivery] Both offers/info and calculateDelivery failed');
                    console.error('[YandexDelivery] calculateDelivery result:', calc);
                    YandexDeliveryUtils.setTextContent(costEl, calc?.error || 'Не удалось рассчитать доставку');
                    if (errorBlock) {
                        errorBlock.textContent = `Ошибка расчета: ${calc?.error || 'Неизвестная ошибка'}`;
                        show(errorBlock);
                    }
                    if (offersContainer) hide(offersContainer);
                    // Затемняем карту при ошибке
                    setMapOverlay(true);
                }
            }
        } else {
            // Для курьера — старый расчет
            calc = await calculateDelivery(coords, address, state.selectedType, state.selectedPvzId);

            console.log('[YandexDelivery] calculateDelivery result:', calc);

            if (calc.success && calc.price != null && parseFloat(calc.price) > 0) {
                state.estimatedCost = parseFloat(calc.price);
                // Сохраняем claim_id для Express API (чтобы использовать при оформлении)
                if (calc.claim_id && state.selectedType === 'courier') {
                    state.expressClaimId = calc.claim_id;
                    console.log('[YandexDelivery] Express claim ID saved:', state.expressClaimId);
                }
                YandexDeliveryUtils.setTextContent(costEl, `${YandexDeliveryUtils.formatPrice(calc.price)} ₽`);
                YandexDeliveryUtils.setTextContent(etaEl, calc.delivery_days ? `(${calc.delivery_days} дн.)` : '');
                YandexDeliveryUtils.setTextContent(etaLabelEl, calc.delivery_days ? ` ETA: ${calc.delivery_days} дн.` : ' ETA: ');

                // Показываем блок с рассчитанной стоимостью
                if (state.selectedType === 'courier') {
                    showCourierDeliveryCost(calc);
                }

                // Активируем кнопку подтверждения
                updateConfirmButton();
            }
        }

        // Обработка ошибки для курьера (не для ПВЗ/Постомат — там свой handling)
        if (state.selectedType !== 'pvz' && state.selectedType !== 'postomat' && calc && !calc.success) {
            console.error('[YandexDelivery] Delivery calculation failed:', calc);
            const errorMsg = calc.error || 'Не удалось рассчитать стоимость доставки';
            YandexDeliveryUtils.setTextContent(costEl, errorMsg);
            if (confirmBtn) confirmBtn.disabled = true;
        }
    }

    /* ==================== Map Overlay ==================== */
    function setMapOverlay(show) {
        const container = $('#yandexDeliveryWidgetContainer');
        if (container) {
            container.classList.toggle('has-offers-error', show);
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
