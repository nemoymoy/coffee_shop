/**
 * Coffee Shop — Yandex Delivery Modal Widget.
 *
 * Управляет модальным окном выбора доставки:
 * 1. Открытие модального окна по кнопке #openDeliveryModal
 * 2. Выбор типа доставки (courier / pvz / postomat)
 * 3. Ввод адреса и расчёт стоимости
 * 4. Подтверждение выбора и обновление полей формы
 */
var YandexDeliveryWidget = (function () {

    /* ==================== State ==================== */

    var state = {
        selectedType: null,
        selectedAddress: '',
        selectedCoords: '',
        selectedPvzId: '',
        selectedPvzName: '',
        estimatedCost: 0,
        modalInstance: null,
        step: 1,
        yandexWidgetLoaded: false,
        yandexWidgetInitialized: false,
        selectedPlacemark: null,
        mapInstance: null
    };

    /* ==================== Config ==================== */

    var CONFIG = {
        CALCULATE_DELIVERY_URL: '/checkout/calculate-delivery/',
        GEOCODE_URL: '/checkout/geocode-address/',
        GEOCODE_DEBOUNCE_MS: 800
    };

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

    /* ==================== Modal Management ==================== */

    function initModal() {
        var modalEl = document.getElementById('deliveryModal');
        if (!modalEl) {
            console.error('[YandexDeliveryModal] Modal #deliveryModal not found');
            return;
        }

        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            state.modalInstance = new bootstrap.Modal(modalEl, {
                backdrop: true,
                keyboard: true
            });
        } else {
            console.warn('[YandexDeliveryModal] Bootstrap Modal not available');
            return;
        }

        // Сброс шагов при открытии
        modalEl.addEventListener('show.bs.modal', function () {
            resetModal();
            showStep(1);
        });

        // Подтверждение выбора
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', handleConfirm);
        }

        // Выбор типа доставки → переход к шагу 2
        var typeRadios = $$('.form-check input[name="yandex_delivery_type"]');
        for (var i = 0; i < typeRadios.length; i++) {
            (function (radio) {
                radio.addEventListener('change', function () {
                    state.selectedType = this.value;
                    // Разблокируем кнопку только если уже есть расчёт (шаг 3)
                    updateConfirmButtonState();
                    // Переходим к шагу ввода адреса
                    showStep(2);
                });
            })(typeRadios[i]);
        }

        // Слушатель закрытия модалки (крестик/отмена)
        modalEl.addEventListener('hidden.bs.modal', function () {
            // Сбрасываем поля формы если пользователь отменил
            resetModal();
        });

        // Обработка ввода адреса для расчёта
        initAddressHandling();
    }

    /* ==================== Step Navigation ==================== */

    function showStep(stepNumber) {
        state.step = stepNumber;

        var step1 = document.getElementById('deliveryStep1');
        var step2 = document.getElementById('deliveryStep2');
        var step3 = document.getElementById('deliveryStep3');
        var widgetContainer = document.getElementById('yandexDeliveryWidgetContainer');
        var addressInputWrap = document.getElementById('yandexAddressInputWrap');
        var mapWarning = document.getElementById('mapUnavailableWarning');

        // Скрываем все шаги
        hideElement(step1);
        hideElement(step2);
        hideElement(step3);

        switch (stepNumber) {
            case 1:
                showElement(step1);
                break;
            case 2:
                showElement(step2);
                
                // Для курьера — ручной ввод адреса без виджета
                if (state.selectedType === 'courier') {
                    hideElement(widgetContainer);
                    hideElement(mapWarning);
                    showElement(addressInputWrap);
                    break;
                }
                
                // Для ПВЗ/Постомата — загружаем виджет Яндекс Доставки
                hideElement(addressInputWrap);
                hideElement(mapWarning);
                showElement(widgetContainer);
                
                // Всегда пересоздаём iframe для корректной инициализации
                loadYandexWidget();
                break;
            case 3:
                // Шаг 3 показываем только для ПВЗ/Постомат
                if (state.selectedType === 'courier') {
                    // Для курьера — остаёмся на шаге 2 с ценой
                    showElement(step2);
                    hideElement(widgetContainer);
                    showElement(addressInputWrap);
                } else {
                    showElement(step3);
                }
                break;
        }
    }

    /* ==================== Confirm Button State ==================== */

    function updateConfirmButtonState() {
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (!confirmBtn) return;
        // Кнопка активна только если выбран тип И есть расчёт стоимости
        confirmBtn.disabled = !(state.selectedType && state.estimatedCost > 0);
    }

    function resetModal() {
        state.selectedType = null;
        state.selectedAddress = '';
        state.selectedCoords = '';
        state.selectedPvzId = '';
        state.selectedPvzName = '';
        state.estimatedCost = 0;
        state.step = 1;
        resetYandexWidget();

        // Сбрасываем radio-кнопки
        var typeRadios = $$('.form-check input[name="yandex_delivery_type"]');
        for (var i = 0; i < typeRadios.length; i++) {
            typeRadios[i].checked = false;
        }

        // Сбрасываем поле адреса
        var addressInput = document.getElementById('yandexAddressInput');
        if (addressInput) {
            addressInput.value = '';
        }

        // Скрываем автокомплит
        var autocompleteList = document.getElementById('yandexAutocompleteList');
        if (autocompleteList) {
            autocompleteList.innerHTML = '';
            hideElement(autocompleteList);
        }

        // Скрываем блок цены для курьера
        var courierPriceBlock = document.getElementById('courierPriceBlock');
        if (courierPriceBlock) {
            courierPriceBlock.style.display = 'none';
            courierPriceBlock.style.background = '';
            courierPriceBlock.style.color = '';
            courierPriceBlock.innerHTML = '';
        }

        // Сбрасываем стоимость
        var costEl = document.getElementById('widgetCost');
        if (costEl) {
            costEl.textContent = 'Расчёт...';
        }

        // Отключаем кнопку подтверждения
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (confirmBtn) {
            confirmBtn.disabled = true;
        }

        var etaEl = document.getElementById('widgetEta');
        if (etaEl) etaEl.textContent = '';
        var etaLabelEl = document.getElementById('widgetEtaLabel');
        if (etaLabelEl) etaLabelEl.textContent = ' ETA: ';
    }

    /* ==================== Address Handling ==================== */

    function initAddressHandling() {
        var addressInput = document.getElementById('yandexAddressInput');
        var autocompleteList = document.getElementById('yandexAutocompleteList');
        if (!addressInput) return;

        var autocompleteTimeout = null;
        var suggestions = [];

        // Обработка ввода для автокомплита
        addressInput.addEventListener('input', function () {
            var query = this.value.trim();
            
            if (autocompleteTimeout) {
                clearTimeout(autocompleteTimeout);
            }

            // Скрываем автокомплит если мало символов
            if (query.length < 3) {
                hideElement(autocompleteList);
                return;
            }

            autocompleteTimeout = setTimeout(function () {
                fetchSuggestions(query);
            }, 600);
        });

        // Обработка клавиш
        addressInput.addEventListener('keydown', function (e) {
            if (!suggestions.length) return;
            
            var visibleItems = autocompleteList.querySelectorAll('.autocomplete-item');
            if (!visibleItems.length) return;

            var highlighted = autocompleteList.querySelector('.autocomplete-item.selected');
            var currentIndex = Array.from(visibleItems).indexOf(highlighted);

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (highlighted) highlighted.classList.remove('selected');
                var nextIndex = (currentIndex + 1) % visibleItems.length;
                visibleItems[nextIndex].classList.add('selected');
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (highlighted) highlighted.classList.remove('selected');
                var prevIndex = (currentIndex - 1 + visibleItems.length) % visibleItems.length;
                visibleItems[prevIndex].classList.add('selected');
            } else if (e.key === 'Enter') {
                e.preventDefault();
                var selectedItem = autocompleteList.querySelector('.autocomplete-item.selected') || visibleItems[0];
                if (selectedItem) {
                    selectedItem.click();
                }
            } else if (e.key === 'Escape') {
                hideElement(autocompleteList);
            }
        });

        // Клик вне автокомплита закрывает его
        document.addEventListener('click', function (e) {
            if (!autocompleteList.contains(e.target) && e.target !== addressInput) {
                hideElement(autocompleteList);
            }
        });
    }

    function fetchSuggestions(query) {
        var autocompleteList = document.getElementById('yandexAutocompleteList');
        if (!autocompleteList) return;

        autocompleteList.innerHTML = '<div class="autocomplete-item">Поиск...</div>';
        showElement(autocompleteList);

        fetch(CONFIG.GEOCODE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ query: query })
        })
        .then(function (response) { return response.json(); })
        .then(function (geoData) {
            if (geoData.rate_limited || geoData.api_error) {
                autocompleteList.innerHTML = '<div class="autocomplete-item text-warning">⚠️ Сервис подсказок временно недоступен. Введите адрес вручную.</div>';
                showElement(autocompleteList);
                suggestions = [];
                return;
            }

            if (!geoData.success || !geoData.features || !geoData.features.length) {
                autocompleteList.innerHTML = '<div class="autocomplete-item text-muted">Ничего не найдено</div>';
                showElement(autocompleteList);
                suggestions = [];
                return;
            }

            suggestions = geoData.features;
            autocompleteList.innerHTML = '';

            for (var i = 0; i < geoData.features.length; i++) {
                (function (feature) {
                    var item = document.createElement('div');
                    item.className = 'autocomplete-item';
                    item.textContent = feature.text;
                    item.addEventListener('click', function () {
                        var addressInput = document.getElementById('yandexAddressInput');
                        if (addressInput) {
                            addressInput.value = feature.text;
                            state.selectedAddress = feature.text;
                            state.selectedCoords = feature.coords ? feature.coords.join(',') : '';
                        }
                        hideElement(autocompleteList);
                        suggestions = [];
                        // Рассчитываем доставку
                        geocodeAndCalculate(feature.text);
                    });
                    autocompleteList.appendChild(item);
                })(geoData.features[i]);
            }
        })
        .catch(function (err) {
            console.error('[YandexDeliveryModal] Fetch suggestions error:', err);
            autocompleteList.innerHTML = '<div class="autocomplete-item text-warning">Сетевая ошибка. Введите адрес вручную.</div>';
            showElement(autocompleteList);
        })
        .then(function () {
            // Убираем подсветку «Поиск...» после завершения
            var spinner = autocompleteList.querySelector('.spinner-border');
            if (spinner) {
                var parent = spinner.parentElement;
                if (parent) parent.remove();
            }
        });
    }

    /* ==================== Manual Address Geocode ==================== */

    function geocodeAndCalculate(address) {
        var costEl = document.getElementById('widgetCost');
        var etaEl = document.getElementById('widgetEta');
        var etaLabelEl = document.getElementById('widgetEtaLabel');
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        var courierPriceBlock = document.getElementById('courierPriceBlock');

        // Показываем блок цены для курьера
        if (state.selectedType === 'courier' && courierPriceBlock) {
            courierPriceBlock.style.display = 'block';
            courierPriceBlock.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Расчёт стоимости...';
        } else if (costEl) {
            costEl.textContent = 'Геокодинг...';
        }

        // Шаг 1: геокодирование адреса для получения координат
        fetch(CONFIG.GEOCODE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ query: address })
        })
        .then(function (response) { return response.json(); })
        .then(function (geoData) {
            if (!geoData.success || !geoData.features || geoData.features.length === 0) {
                throw new Error(geoData.rate_limited ? 'Сервис геокодинга временно недоступен (rate limit)' : 'Адрес не найден. Проверьте правильность ввода.');
            }

            var firstResult = geoData.features[0];
            var coords = firstResult.coords;
            var formattedAddress = firstResult.text || address;

            if (!coords || coords.length < 2) {
                throw new Error('Сервер верёл адрес без координат. Попробуйте указать адрес подробнее.');
            }

            // Шаг 2: расчёт стоимости с координатами
            if (costEl) {
                costEl.textContent = 'Расчёт...';
            }

            return fetch(CONFIG.CALCULATE_DELIVERY_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    destination_coords: coords.join(','),
                    destination_address: formattedAddress,
                    delivery_type: state.selectedType || 'courier'
                })
            }).then(function (r) { return r.json(); }).then(function (calcData) {
                return {
                    calcData: calcData,
                    address: formattedAddress,
                    coords: coords
                };
            });
        })
        .then(function (result) {
            var calcData = result.calcData;

            if (calcData.success && calcData.price) {
                state.estimatedCost = calcData.price;
                state.selectedAddress = result.address;
                state.selectedCoords = result.coords.join(',');

                // Для курьера — показываем цену в блоке под полем ввода
                if (state.selectedType === 'courier' && courierPriceBlock) {
                    var etaText = calcData.delivery_days ? ('  • ' + calcData.delivery_days + ' дн.') : '';
                    courierPriceBlock.innerHTML = '✅ Стоимость доставки: <strong>' + formatPrice(calcData.price) + ' ₽</strong>' + etaText;
                    courierPriceBlock.style.background = '';
                    courierPriceBlock.style.color = '';
                } else {
                    if (costEl) {
                        costEl.textContent = formatPrice(calcData.price) + ' ₽';
                    }
                    if (etaEl) {
                        etaEl.textContent = calcData.delivery_days ? ('(' + calcData.delivery_days + ' дн.)') : '';
                    }
                    if (etaLabelEl) {
                        etaLabelEl.textContent = calcData.delivery_days ? (' ETA: ' + calcData.delivery_days + ' дн.') : ' ETA: ';
                    }
                }
                updateConfirmButtonState();

                // Для курьера не переходим к шагу 3 — остаёмся на шаге 2
                if (state.selectedType !== 'courier') {
                    showStep(3);
                }
            } else {
                // Показываем реальную ошибку с бэкенда
                var errorMsg = calcData.error || 'Не удалось рассчитать стоимость доставки';
                console.error('[YandexDeliveryModal] Delivery error:', errorMsg, calcData);

                if (state.selectedType === 'courier' && courierPriceBlock) {
                    courierPriceBlock.innerHTML = '❌ ' + errorMsg;
                    courierPriceBlock.style.background = '#ffebee';
                    courierPriceBlock.style.color = '#c62828';
                } else {
                    if (costEl) {
                        costEl.textContent = '❌ ' + errorMsg;
                        costEl.style.color = 'red';
                    }
                }
                if (confirmBtn) {
                    confirmBtn.disabled = true;
                }
            }
        })
        .catch(function (err) {
            console.error('[YandexDeliveryModal] Error:', err);
            var errorMsg = err.message || 'Неизвестная ошибка';

            if (state.selectedType === 'courier' && courierPriceBlock) {
                courierPriceBlock.innerHTML = '❌ ' + errorMsg;
                courierPriceBlock.style.background = '#ffebee';
                courierPriceBlock.style.color = '#c62828';
            } else {
                if (costEl) {
                    costEl.textContent = '❌ ' + errorMsg;
                    costEl.style.color = 'red';
                }
            }
            if (confirmBtn) {
                confirmBtn.disabled = true;
            }
        });
    }

    /* ==================== Confirm Selection ==================== */

    function handleConfirm() {
        if (!state.selectedType) {
            alert('Пожалуйста, выберите способ доставки');
            return;
        }

        // Для ПВЗ/Постомат — проверим, что есть координаты от виджета
        if (state.selectedType !== 'courier') {
            if (!state.selectedPvzId) {
                alert('Пожалуйста, выберите пункт выдачи или постомат');
                return;
            }
            if (!state.selectedCoords) {
                alert('Не удалось получить координаты. Попробуйте выбрать пункт заново.');
                return;
            }
        }

        if (!state.selectedAddress) {
            alert('Пожалуйста, введите адрес доставки');
            return;
        }

        if (state.estimatedCost <= 0) {
            alert('Не удалось рассчитать стоимость доставки');
            return;
        }

        // Обновляем скрытые поля формы
        setFormField('id_delivery_address', state.selectedAddress);
        setFormField('id_yandex_delivery_type', state.selectedType);
        setFormField('id_yandex_station_id', state.selectedPvzId);
        setFormField('id_yandex_station_name', state.selectedPvzName || state.selectedAddress);
        setFormField('id_yandex_delivery_cost', state.estimatedCost);

        // Обновляем видимое поле delivery_address в checkout.js
        var checkoutAddress = document.getElementById('id_delivery_address');
        if (checkoutAddress) {
            checkoutAddress.value = state.selectedAddress;
        }

        // Обновляем сводку доставки
        updateDeliverySummary();

        // Закрываем модальное окно
        closeModal();
    }

    /* ==================== Delivery Summary Update ==================== */

    function updateDeliverySummary() {
        var deliveryInfo = document.getElementById('deliveryInfo');
        var typeEl = document.getElementById('selectedDeliveryType');
        var addressEl = document.getElementById('selectedDeliveryAddress');
        var costEl = document.getElementById('selectedDeliveryCost');
        var etaEl = document.getElementById('selectedDeliveryEta');
        var orderGoodsTotal = document.getElementById('orderGoodsTotal');
        var orderDeliveryCost = document.getElementById('orderDeliveryCost');
        var checkoutTotal = document.getElementById('checkoutTotal');

        if (!deliveryInfo) return;

        var typeLabel = getConfiguredTypeLabel(state.selectedType);

        if (typeEl) typeEl.textContent = typeLabel;
        if (addressEl) addressEl.textContent = state.selectedAddress;
        if (costEl) costEl.textContent = formatPrice(state.estimatedCost) + ' ₽';
        if (etaEl) etaEl.textContent = '';

        deliveryInfo.style.display = 'block';

        // Обновляем стоимость доставки в карточке заказа
        if (orderDeliveryCost) {
            orderDeliveryCost.textContent = state.estimatedCost ? (formatPrice(state.estimatedCost) + ' ₽') : '— ₽';
        }

        // Пересчитываем итог
        if (orderGoodsTotal && checkoutTotal && state.estimatedCost > 0) {
            var goodsText = orderGoodsTotal.textContent.replace(/[^0-9.,]/g, '').replace(',', '.');
            var goodsTotal = parseFloat(goodsText) || 0;
            var newTotal = goodsTotal + state.estimatedCost;
            checkoutTotal.textContent = formatPrice(newTotal) + ' ₽';
        }
    }

    function getConfiguredTypeLabel(type) {
        var labels = {
            'courier': '🚗 Курьер',
            'pvz': '📦 Пункт выдачи (ПВЗ)',
            'postomat': '📮 Постомат'
        };
        return labels[type] || labels['courier'];
    }

    /* ==================== Form Field Helpers ==================== */

    function setFormField(fieldId, value) {
        var field = document.getElementById(fieldId);
        if (field) {
            field.value = value;
        }
    }

    function getCsrfToken() {
        var tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenInput) {
            return tokenInput.value;
        }
        var name = 'csrftoken';
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
        return cookieValue || '';
    }

    /* ==================== Cost Calculation ==================== */

    function calculateDeliveryCost(coords, address) {
        var costEl = document.getElementById('widgetCost');
        var etaEl = document.getElementById('widgetEta');
        var etaLabelEl = document.getElementById('widgetEtaLabel');
        var confirmBtn = document.getElementById('confirmDeliveryBtn');

        if (!coords || coords.length === 0) {
            if (costEl) costEl.textContent = 'Координаты не получены';
            return;
        }

        if (costEl) {
            costEl.textContent = 'Расчёт...';
        }

        fetch(CONFIG.CALCULATE_DELIVERY_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                destination_coords: coords,
                destination_address: address || state.selectedAddress,
                pvz_id: state.selectedPvzId,
                delivery_type: state.selectedType === 'pvz' ? 'pickup' : 'courier'
            })
        })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.success && data.price) {
                state.estimatedCost = data.price;

                if (costEl) {
                    costEl.textContent = formatPrice(data.price) + ' ₽';
                }
                if (etaEl) {
                    etaEl.textContent = data.delivery_days ? '(' + data.delivery_days + ' дн.)' : '';
                }
                if (etaLabelEl) {
                    etaLabelEl.textContent = data.delivery_days ? (' ETA: ' + data.delivery_days + ' дн.') : ' ETA: ';
                }
                updateConfirmButtonState();

                // Автопереход к шагу 3
                showStep(3);
            } else {
                if (costEl) {
                    costEl.textContent = data.error || 'Не удалось рассчитать';
                }
                if (confirmBtn) {
                    confirmBtn.disabled = true;
                }
            }
        })
        .catch(function (err) {
            console.error('[YandexDeliveryModal] Calculate cost error:', err);
            if (costEl) {
                costEl.textContent = 'Ошибка подключения';
            }
            if (confirmBtn) {
                confirmBtn.disabled = true;
            }
        });
    }

    /* ==================== Yandex Widget Loading ==================== */

    function loadYandexWidget() {
        // Используем Яндекс Карты API для поиска ПВЗ и постоматов
        if (state.yandexWidgetLoaded) {
            initYandexMap();
            return;
        }

        var existing = document.getElementById('yandex-maps-api-script');
        if (existing) {
            console.warn('[YandexDeliveryModal] Yandex Maps API already loaded');
            state.yandexWidgetLoaded = true;
            setTimeout(initYandexMap, 100);
            return;
        }

        var apiKey = window.YANDEX_JAVASCRIPT_API_KEY || window.YANDEX_GEOCODER_API_KEY;
        if (!apiKey) {
            console.error('[YandexDeliveryModal] No YMaps API key found');
            state.yandexWidgetLoaded = false;
            showErrorInModal('Не настроен API-ключ Яндекс Карт. Попробуйте ввести адрес вручную.');
            showManualAddressFallback();
            return;
        }

        console.log('[YandexDeliveryModal] Loading Yandex Maps API...');
        var script = document.createElement('script');
        script.id = 'yandex-maps-api-script';
        script.src = 'https://api-maps.yandex.ru/2.1/?apikey=' + apiKey + '&lang=ru_RU';
        script.async = true;

        script.onload = function () {
            console.log('[YandexDeliveryModal] Yandex Maps API loaded');
            state.yandexWidgetLoaded = true;
            // Ждём готовности ymaps
            if (typeof ymaps !== 'undefined' && ymaps.ready) {
                ymaps.ready(initYandexMap);
            } else {
                setTimeout(initYandexMap, 500);
            }
        };

        script.onerror = function () {
            console.error('[YandexDeliveryModal] Failed to load Yandex Maps API');
            state.yandexWidgetLoaded = false;
            showErrorInModal('Не удалось загрузить Яндекс Карты. Попробуйте ввести адрес вручную.');
            showManualAddressFallback();
        };

        document.head.appendChild(script);
    }

    function initPostMessageListener() {
        window.addEventListener('message', function (event) {
            // Яндекс Доставка отправляет данные только с своих доменов
            if (event.origin !== 'https://dostavka.yandex.ru' &&
                event.origin !== 'https://delivery.yandex.ru' &&
                event.origin !== 'https://www.yandex.ru') {
                return;
            }

            var data = event.data;
            if (!data) return;

            // Обрабатываем выбранный пункт
            if (data.type === 'point_selected' || data.pointId || data.point_id) {
                var point = {
                    id: data.pointId || data.point_id || data.id || '',
                    name: data.name || data.title || data.pointName || '',
                    address: data.address || data.full_address || '',
                    coordinates: data.coordinates || data.coords || data.center || '',
                };

                if (point.id) {
                    console.log('[YandexDeliveryModal] Point selected via postMessage:', point);
                    handleYandexPointSelected(point);
                }
            }
        });
    }

    function initYandexMap() {
        console.log('[YandexDeliveryModal] initYandexMap called');
        console.log('[YandexDeliveryModal] ymaps available:', typeof ymaps);

        if (typeof ymaps === 'undefined') {
            console.warn('[YandexDeliveryModal] ymaps not ready yet, retrying...');
            setTimeout(initYandexMap, 200);
            return;
        }

        var container = document.getElementById('delivery-widget');
        if (!container) {
            console.error('[YandexDeliveryModal] Container #delivery-widget not found');
            return;
        }

        // Очищаем предыдущую карту если есть
        if (state.mapInstance) {
            state.mapInstance.destroy();
            state.mapInstance = null;
        }

        try {
            // Определяем тип точек для поиска
            var searchType = state.selectedType === 'pvz' ? 'shop' : 'store';
            // Ищем широко — все пункты выдачи и постоматы в Самаре
            var query = state.selectedType === 'pvz' 
                ? 'пункт выдачи выдачи Самара OzON Wildberries Yandex Market' 
                : 'постомат выдачи Самбер Яндекс Ozon Wildberries';

            console.log('[YandexDeliveryModal] Creating map, searchType:', searchType);

            // Загружаем координаты магазина из конфигурации
            var shopLat = window.YANDEX_SHOP_LAT !== undefined ? window.YANDEX_SHOP_LAT : 53.216940239129094;
            var shopLon = window.YANDEX_SHOP_LON !== undefined ? window.YANDEX_SHOP_LON : 50.162688008923745;

            // Создаём карту
            ymaps.ready(function () {
                state.mapInstance = new ymaps.Map('delivery-widget', {
                    center: [shopLat, shopLon], // Координаты магазина
                    zoom: 14,
                    controls: ['zoomControl', 'fullscreenControl']
                }, {
                    suppressMapOpenBlock: true // Отключаем блоки кнопок по умолчанию
                });

                // Добавляем метку магазина
                var shopPlacemark = new ymaps.Placemark([shopLat, shopLon], {
                    hintContent: 'Магазин: ул. Революционная, д. 3',
                    balloonContent: '📍 ул. Революционная, д. 3<br>Самара'
                }, {
                    preset: 'islands#blueCoffeeIcon'
                });
                state.mapInstance.geoObjects.add(shopPlacemark);

                // Клик по карте — выбор адреса
                state.mapInstance.events.add('click', function (e) {
                    var coords = e.get('coords');
                    console.log('[YandexDeliveryModal] Map clicked at:', coords);
                    
                    // Геокодинг обратный — получаем адрес по координатам
                    ymaps.geocode(coords, {
                        results: 1,
                        kind: 'house'
                    }).then(function (res) {
                        var firstObject = res.geoObjects.get(0);
                        if (firstObject) {
                            var address = firstObject.properties.get('fullName') || firstObject.properties.get('text');
                            var placemarkCoords = firstObject.geometry.getCoordinates();
                            
                            // Добавляем метку выбранного адреса
                            var selectedPlacemark = new ymaps.Placemark(placemarkCoords, {
                                hintContent: address,
                                balloonContent: '✅ Выберите этот адрес'
                            }, {
                                preset: 'islands#redDeliveryIcon'
                            });
                            
                            // Удаляем предыдущую метку выбора если есть
                            if (state.selectedPlacemark) {
                                state.mapInstance.geoObjects.remove(state.selectedPlacemark);
                            }
                            state.mapInstance.geoObjects.add(selectedPlacemark);
                            state.selectedPlacemark = selectedPlacemark;
                            
                            // Автоматически выбираем этот адрес
                            var pointData = {
                                id: '',
                                name: 'Выбранный адрес',
                                address: address,
                                coordinates: placemarkCoords
                            };
                            handleYandexPointSelected(pointData);
                            
                            // Закрываем балун метки магазина
                            shopPlacemark.balloon.close();
                        }
                    }).catch(function (err) {
                        console.error('[YandexDeliveryModal] Reverse geocode error:', err);
                    });
                });

                // Поиск точек доставки после готовности карты
                searchDeliveryPoints(searchType, query);

                state.yandexWidgetInitialized = true;
                console.log('[YandexDeliveryModal] Map created successfully at shop coords:', [shopLat, shopLon]);
            });
        } catch (e) {
            console.error('[YandexDeliveryModal] Failed to create map:', e);
            showErrorInModal('Не удалось инициализировать карту. Попробуйте ввести адрес вручную.');
            showManualAddressFallback();
        }
    }

    function searchDeliveryPoints(type, query) {
        if (!state.mapInstance) {
            console.error('[YandexDeliveryModal] Map not initialized');
            return;
        }

        console.log('[YandexDeliveryModal] Searching delivery points:', query);

        // Используем геопоиск для поиска точек
        ymaps.geocode(query, {
            results: 30,
            resultsPerRegion: 30
        }).then(function (res) {
            var geoObjects = res.geoObjects;
            var count = 0;

            // Считаем объекты правильно
            geoObjects.each(function () {
                count++;
            });

            console.log('[YandexDeliveryModal] Found ' + count + ' delivery points');

            geoObjects.each(function (geoObject) {
                var name = geoObject.properties.get('name') || geoObject.properties.get('fullName') || '';
                var desc = geoObject.properties.get('description') || geoObject.properties.get('text') || '';
                var coords = geoObject.geometry.getCoordinates();

                // Ставим метки на карты
                var iconCaption = name ? name.substring(0, 30) : 'ПВЗ';
                geoObject.options.set('preset', 'islands#blueDeliveryIcon');
                geoObject.properties.set('iconCaption', iconCaption);

                geoObject.events.add('click', function (e) {
                    var pointData = {
                        id: geoObject.properties.get('id') || '',
                        name: name,
                        address: desc,
                        coordinates: coords
                    };

                    console.log('[YandexDeliveryModal] Point clicked:', pointData);
                    handleYandexPointSelected(pointData);
                    e.stopPropagation();
                });
            });

            // Если точки найдены — центрируем карту на них
            if (count > 0) {
                var bounds = geoObjects.getBounds();
                if (bounds) {
                    state.mapInstance.setBounds(bounds, { checkZoomRange: true });
                }
            } else {
                console.warn('[YandexDeliveryModal] No delivery points found, showing manual input fallback');
            }
        }).catch(function (err) {
            console.error('[YandexDeliveryModal] Geocode error:', err);
            // Если геопоиск не нашёл, показываем ручной ввод
            showErrorInModal('Точки доставки не найдены. Попробуйте ввести адрес вручную.');
        });
    }

    function handleYandexPointSelected(point) {
        console.log('[YandexDeliveryModal] Point selected:', point);
        
        state.selectedPvzId = point.id || '';
        state.selectedPvzName = point.name || point.address || '';
        state.selectedAddress = point.address || state.selectedPvzName;
        
        // Координаты из Яндекс Карт уже массив [lat, lon]
        var coords = point.coordinates;
        if (Array.isArray(coords)) {
            state.selectedCoords = coords.join(',');
        } else if (typeof coords === 'string') {
            state.selectedCoords = coords;
        } else {
            state.selectedCoords = '';
        }

        var costEl = document.getElementById('widgetCost');
        var confirmBtn = document.getElementById('confirmDeliveryBtn');

        if (costEl) {
            costEl.textContent = 'Расчёт...';
        }
        if (confirmBtn) {
            confirmBtn.disabled = true;
        }

        // Рассчитываем стоимость доставки
        calculateDeliveryCost(state.selectedCoords, state.selectedAddress);
    }

    function showErrorInModal(message) {
        var mapWarning = document.getElementById('mapUnavailableWarning');
        if (mapWarning) {
            mapWarning.querySelector('p').textContent = message + ' Введите адрес вручную для расчёта доставки.';
            showElement(mapWarning);
        }
        showManualAddressFallback();
    }

    function showManualAddressFallback() {
        hideElement(document.getElementById('yandexDeliveryWidgetContainer'));
        showElement(document.getElementById('yandexAddressInputWrap'));
        state.yandexWidgetLoaded = false;
        state.yandexWidgetInitialized = false;
    }

    function resetYandexWidget() {
        state.yandexWidgetLoaded = false;
        state.yandexWidgetInitialized = false;
        
        // Удаляем метку выбранного адреса
        if (state.selectedPlacemark && state.mapInstance) {
            state.mapInstance.geoObjects.remove(state.selectedPlacemark);
        }
        state.selectedPlacemark = null;
        
        // Очищаем карту
        if (state.mapInstance) {
            state.mapInstance.destroy();
            state.mapInstance = null;
        }
        
        var container = document.getElementById('delivery-widget');
        if (container) {
            container.innerHTML = '';
        }
    }

    /* ==================== Modal Control ==================== */

    function openModal() {
        if (state.modalInstance) {
            state.modalInstance.show();
        } else {
            console.error('[YandexDeliveryModal] Modal not initialized');
        }
    }

    function closeModal() {
        if (state.modalInstance) {
            state.modalInstance.hide();
        }
    }

    /* ==================== Public API ==================== */

    function init() {
        initModal();
        initPostMessageListener();

        // Подключаем кнопку открытия модального окна
        var openBtn = document.getElementById('openDeliveryModal');
        if (openBtn) {
            openBtn.addEventListener('click', function (e) {
                e.preventDefault();
                openModal();
            });
        }
    }

    function getSelectedType() {
        return state.selectedType;
    }

    function getSelectedAddress() {
        return state.selectedAddress;
    }

    function getEstimatedCost() {
        return state.estimatedCost;
    }

    function formatPrice(price) {
        return parseFloat(price).toLocaleString('ru-RU', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        });
    }

    return {
        init: init,
        openModal: openModal,
        closeModal: closeModal,
        getSelectedType: getSelectedType,
        getSelectedAddress: getSelectedAddress,
        getEstimatedCost: getEstimatedCost,
        _handlePointSelected: handleYandexPointSelected,
    };

})();

document.addEventListener('DOMContentLoaded', YandexDeliveryWidget.init);

/**
 * Глобальный callback для Yandex Delivery widget.
 * Вызывается виджетом при выборе пункта выдачи/постомата.
 */
window.YandexDeliveryCallback = function (pointData) {
    console.log('[YandexDeliveryModal] YandexDeliveryCallback:', pointData);

    var pointId = pointData.pointId || pointData.id || '';
    var pointType = pointData.pointType || pointData.type || '';
    var pointName = pointData.name || pointData.title || '';
    var pointAddress = pointData.address || pointData.full_address || '';

    if (!pointId) {
        console.warn('[YandexDeliveryModal] No point ID in callback data');
        return;
    }

    // Обновляем состояние модуля
    YandexDeliveryWidget._handlePointSelected({
        id: pointId,
        name: pointName,
        address: pointAddress,
    });
};
