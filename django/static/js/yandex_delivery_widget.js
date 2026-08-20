/**
 * Coffee Shop — Yandex Delivery Widget.
 * Модальный виджет выбора доставки через Яндекс Доставку:
 * 1. Выбор типа доставки (курьер / ПВЗ / постомат)
 * 2. Ввод адреса с autocomplete через Яндекс Карты API
 * 3. Расчёт стоимости и ETA
 * 4. Возврат данных на страницу оформления заказа
 */
var YandexDeliveryWidget = (function () {

    /* ==================== Состояние виджета ==================== */

    var modal = null;
    var bootstrapModal = null;
    var autocomplete = null;
    var selectedType = null;   // 'courier', 'pvz', 'postomat'
    var selectedAddress = null;
    var selectedPrice = null;
    var selectedEta = null;
    var yandexMapsInitialized = false;
    var hasAccessToken = false;
    var yamap = null;
    var mapInstance = null;
    var pointObjects = [];
    var selectedPoint = null;
    var currentCenter = [55.751574, 37.573856];  // Москва по умолчанию

    /* ==================== Инициализация ==================== */

    function getCookie(name) {
        var cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {
                var cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === name + '=') {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function init() {
        console.log('YandexDeliveryWidget: init called');
        
        modal = document.getElementById('deliveryModal');
        if (!modal) {
            console.error('YandexDeliveryWidget: modal #deliveryModal not found');
            return;
        }
        console.log('YandexDeliveryWidget: modal found');

        if (typeof bootstrap === 'undefined') {
            console.error('YandexDeliveryWidget: bootstrap is not loaded');
            return;
        }
        
        try {
            bootstrapModal = new bootstrap.Modal(modal);
            console.log('YandexDeliveryWidget: bootstrap modal initialized');
        } catch (e) {
            console.error('YandexDeliveryWidget: failed to init modal:', e);
            return;
        }

        // Проверка наличия OAuth токена
        hasAccessToken = checkAccessToken();
        console.log('YandexDeliveryWidget: hasAccessToken =', hasAccessToken);

        // Привязка событий
        bindEvents();

        // Инициализация Яндекс Карт (если ключ настроен)
        initYandexMaps();
    }

    function checkAccessToken() {
        // Проверяем, есть ли данные о токене (через data-атрибут или глобальную переменную)
        if (modal) {
            var hasToken = modal.getAttribute('data-has-token');
            return hasToken === 'true';
        }
        return false;
    }

    function initYandexMaps() {
        // Проверка наличия ключа API
        var mapsScript = document.querySelector('script[src*="api-maps.yandex.ru"]');
        if (mapsScript) {
            // Скрипт Яндекс Карт подключён
            if (typeof ymaps3 !== 'undefined') {
                yandexMapsInitialized = true;
                console.log('✅ Yandex Maps already loaded');
            } else {
                // Ж загрузки ymaps3
                console.log('⏳ Waiting for ymaps3 to load...');
                var checkInterval = setInterval(function() {
                    if (typeof ymaps3 !== 'undefined') {
                        clearInterval(checkInterval);
                        ymaps3.ready(function() {
                            yandexMapsInitialized = true;
                            console.log('✅ ymaps3.ready() completed');
                            if (selectedType && selectedType !== 'courier') {
                                initYandexMapForPvz();
                            }
                        });
                    }
                }, 100);
            }
        }
    }

    function handleYMapsReady() {
        yandexMapsInitialized = true;
        // Autocomplete инициализируется при открытии модального окна
    }

    function loadGeocoder() {
        console.log('✅ Geocoder available via REST API');
        return Promise.resolve();
    }

    function getMapApiKey() {
        // Карта требует JavaScript API ключ
        if (window.YANDEX_JAVASCRIPT_API_KEY) {
            return window.YANDEX_JAVASCRIPT_API_KEY;
        }
        if (window.YANDEX_MAPS_API_KEY) {
            return window.YANDEX_MAPS_API_KEY;
        }
        return '';
    }

    function loadYandexMaps() {
        var apiKey = getMapApiKey();
        if (!apiKey) {
            console.warn('YandexDeliveryWidget: No API key found');
            return Promise.reject(new Error('No API key'));
        }
        
        return new Promise(function(resolve, reject) {
            if (typeof ymaps3 !== 'undefined') {
                resolve(ymaps3);
                return;
            }
            
            var script = document.createElement('script');
            script.src = 'https://api-maps.yandex.ru/3.0/?apikey=' + apiKey + '&lang=ru_RU';
            script.onload = function() {
                if (typeof ymaps3 !== 'undefined') {
                    ymaps3.ready(function() {
                        yandexMapsInitialized = true;
                        resolve(ymaps3);
                    });
                } else {
                    reject(new Error('ymaps3 not loaded'));
                }
            };
            script.onerror = function() {
                reject(new Error('Failed to load Yandex Maps'));
            };
            document.head.appendChild(script);
        });
    }

    /* ==================== События ==================== */

    function bindEvents() {
        // Открывающая кнопка
        var openBtn = document.getElementById('openDeliveryModal');
        if (openBtn) {
            openBtn.addEventListener('click', function(e) {
                e.preventDefault();
                console.log('YandexDeliveryWidget: opening modal');
                openModal();
            });
            console.log('YandexDeliveryWidget: button bound');
        } else {
            console.warn('YandexDeliveryWidget: button #openDeliveryModal not found');
        }

        // Радио-кнопки типа доставки
        var deliveryTypeRadios = document.querySelectorAll('input[name="yandex_delivery_type"]');
        deliveryTypeRadios.forEach(function (radio) {
            radio.addEventListener('change', handleTypeChange);
        });

        // Кнопка подтверждения
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', confirmDelivery);
        }

        // Сброс состояния при закрытии модалки
        modal.addEventListener('hidden.bs.modal', function () {
            console.log('YandexDeliveryWidget: modal hidden');
            resetWidget();
        });
        
        modal.addEventListener('shown.bs.modal', function () {
            console.log('YandexDeliveryWidget: modal shown');
            // Инициализируем autocomplete при открытии
            initAddressAutocomplete();
        });
    }

    /* ==================== Открытие/закрытие ==================== */

    function openModal() {
        console.log('YandexDeliveryWidget: openModal called, hasAccessToken:', hasAccessToken);

        // Сбросить состояние
        resetWidget();

        // Показать предупреждение о подключении, если нет токена
        if (!hasAccessToken) {
            var modalBody = document.querySelector('#deliveryModal .modal-body');
            if (modalBody) {
                var warningDiv = document.getElementById('yandexDeliveryWarning');
                if (warningDiv) {
                    warningDiv.style.display = 'block';
                }
            }
        }

        // Показать модалку
        if (bootstrapModal) {
            console.log('YandexDeliveryWidget: showing modal');
            bootstrapModal.show();
        } else {
            console.error('YandexDeliveryWidget: bootstrapModal is null');
        }
    }

    function closeModal() {
        if (bootstrapModal) {
            bootstrapModal.hide();
        }
    }

    /* ==================== Шаг 1: Выбор типа доставки ==================== */

    function handleTypeChange(e) {
        selectedType = e.target.value;

        // Обновить видимость шагов
        updateStepVisibility();

        // Если адрес уже выбран — пересчитать
        if (selectedAddress) {
            calculateDelivery();
        }

        // Сбросить подтверждение
        updateConfirmButton();
    }

    function updateStepVisibility() {
        var step2 = document.getElementById('deliveryStep2');
        var step3 = document.getElementById('deliveryStep3');
        var mapContainer = document.getElementById('yandexMapContainer');
        var addressWrap = document.getElementById('yandexAddressInputWrap');
        var mapUnavailable = document.getElementById('mapUnavailableWarning');

        if (step2) step2.style.display = 'block';

        if (selectedType === 'courier') {
            // Для курьерской доставки — только адрес
            if (mapContainer) mapContainer.style.display = 'none';
            if (addressWrap) addressWrap.style.display = 'block';
            if (mapUnavailable) mapUnavailable.style.display = 'none';
        } else {
            // Для ПВЗ и постомата — карта с точками
            if (mapContainer) mapContainer.style.display = 'block';
            if (addressWrap) addressWrap.style.display = 'block';
            if (mapUnavailable) mapUnavailable.style.display = 'none';
            
            // Инициализируем карту если нужно
            if (typeof ymaps3 !== 'undefined') {
                initYandexMapForPvz();
            }
        }

        if (step3) {
            step3.style.display = selectedAddress ? 'block' : 'none';
        }
    }

    /* ==================== Шаг 2: Ввод адреса ==================== */

    var addressAutocompleteTimeout = null;
    var lastAutocompleteTime = 0;
    var REQUEST_THROTTLE = 1500; // Минимальный интервал между запросами (1.5 сек)
    var REQUEST_DEBOUNCE = 800;  // Debounce при вводе (800 мс)

    function initAddressAutocomplete() {
        var input = document.getElementById('yandexAddressInput');
        if (!input) return;

        console.log('🔍 initAddressAutocomplete: attaching input handler');

        // Удаляем старый обработчик если был
        if (input._autocompleteHandler) {
            input.removeEventListener('input', input._autocompleteHandler);
        }

        // Создаём новый обработчик
        input._autocompleteHandler = function() {
            // Очищаем предыдущий таймаут
            if (addressAutocompleteTimeout) {
                clearTimeout(addressAutocompleteTimeout);
            }

            var query = input.value.trim();
            var list = document.getElementById('yandexAutocompleteList');
            if (!list) return;

            // Если пустой запрос - скрываем список
            if (query.length === 0) {
                list.style.display = 'none';
                list.innerHTML = '';
                return;
            }

            // Debounce + throttle
            addressAutocompleteTimeout = setTimeout(function() {
                var now = Date.now();
                var timeSinceLastRequest = now - lastAutocompleteTime;
                
                // Если запрос был недавно — ждём
                if (timeSinceLastRequest < REQUEST_THROTTLE) {
                    var waitTime = REQUEST_THROTTLE - timeSinceLastRequest;
                    console.log('⏳ Throttling autocomplete request, waiting', waitTime, 'ms');
                    setTimeout(function() {
                        console.log('🔍 Autocomplete query:', query);
                        doAutocomplete(query);
                    }, waitTime);
                } else {
                    console.log('🔍 Autocomplete query:', query);
                    doAutocomplete(query);
                }
            }, REQUEST_DEBOUNCE);
        };

        // Подключаем обработчик
        input.addEventListener('input', input._autocompleteHandler);
        console.log('✅ Autocomplete handler attached');
    }

    function doAutocomplete(query) {
        var list = document.getElementById('yandexAutocompleteList');
        var input = document.getElementById('yandexAddressInput');
        if (!list || !input) return;

        console.log('🔍 doAutocomplete called with query:', query);

        // Очищаем список
        list.innerHTML = '';

        // Прокси запрос к Django backend (обход CORS)
        fetch('/checkout/geocode-address/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({ query: query }),
        })
        .then(function(response) {
            console.log('📡 Geocoder proxy response status:', response.status);
            return response.json();
        })
        .then(function(data) {
            console.log('📦 Geocoder proxy data:', data);
            list.innerHTML = '';
            lastAutocompleteTime = Date.now();

            if (data.success && data.features && data.features.length > 0) {
                var features = data.features;
                console.log('✅ Found', features.length, 'results');

                features.forEach(function(item) {
                    var text = item.text;
                    var coords = item.coords;  // [longitude, latitude]

                    if (!text) return;

                    console.log('  📍 Result:', text, 'Coords:', coords);

                    var itemEl = document.createElement('div');
                    itemEl.className = 'autocomplete-item';
                    itemEl.textContent = text;

                    itemEl.addEventListener('click', function() {
                        console.log('📍 Selected address:', text);
                        input.value = text;
                        list.style.display = 'none';
                        selectedAddress = text;

                        if (coords && yamap && yamap.map) {
                            // Яндекс Maps использует [lat, lon]
                            currentCenter = [parseFloat(coords[1]), parseFloat(coords[0])];
                            yamap.map.setLocation({ center: currentCenter, zoom: 15 });
                            placeSingleMarker(currentCenter, text);
                        }

                        calculateDelivery();
                    });

                    list.appendChild(itemEl);
                });

                if (list.children.length > 0) {
                    list.style.display = 'block';
                } else {
                    list.innerHTML = '<div class="autocomplete-item text-warning">Ничего не найдено</div>';
                    list.style.display = 'block';
                }
            } else if (data.error) {
                console.error('❌ Geocoder error:', data.error);
                list.innerHTML = '<div class="autocomplete-item text-warning">⚠️ ' + data.error + '</div>';
                list.style.display = 'block';
            } else {
                console.warn('⚠️ No results in geocoder response');
                list.innerHTML = '<div class="autocomplete-item text-warning">Ничего не найдено</div>';
                list.style.display = 'block';
            }
        })
        .catch(function(err) {
            console.error('❌ Geocoder proxy error:', err);
            list.innerHTML = '<div class="autocomplete-item text-danger">Ошибка соединения</div>';
            list.style.display = 'block';
        });
    }

    function showMockSamaraResults(query, list, input) {
        console.log('⚠️ Using mock Samara results');
        var mockResults = [
            'Самара, ул. Революционная, д. 3',
            'Самара, ул. Революционная, д. 5',
            'Самара, ул. Революционная, д. 10',
            'Самара, пл. Ленина',
            'Самара, ул. Советская, д. 1',
            'Самара, пр. Мира, д. 20',
            'Самара, ул. Молодогвардейская, д. 198',
            'Самара, ул. Чайковского, д. 106'
        ];
        
        mockResults.forEach(function(address) {
            var itemEl = document.createElement('div');
            itemEl.className = 'autocomplete-item';
            itemEl.textContent = address;
            
            itemEl.addEventListener('click', function() {
                console.log('📍 Selected mock address:', address);
                input.value = address;
                list.style.display = 'none';
                selectedAddress = address;
                calculateDelivery();
            });
            
            list.appendChild(itemEl);
        });
        
        list.style.display = 'block';
    }

    function placeSingleMarker(coords, text) {
        if (!yamap || !yamap.map) {
            console.warn('Map not available for single marker');
            return;
        }
        
        // Удаляем старые маркеры
        pointObjects.forEach(function(obj) {
            try {
                if (obj && obj.unlink) obj.unlink();
            } catch(e) {}
        });
        pointObjects = [];
        
        var icon = '<div style="width:30px;height:30px;background:#FF6B6B;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.3);">📍</div>';
        
        try {
            var YMapMarker = ymaps3.YMapMarker;
            var marker = new YMapMarker({
                coordinates: coords,
                icon: icon
            });
            
            yamap.map.addChild(marker);
            
            marker.events.add('click', function() {
                selectedAddress = text;
                document.getElementById('yandexAddressInput').value = text;
                calculateDelivery();
            });
            
            pointObjects.push(marker);
        } catch(e) {
            console.warn('Failed to add single marker:', e);
        }
    }

    function getMapsApiKey() {
        // Геокодер использует ключ GeoCoder (REST API)
        if (window.YANDEX_GEOCODER_API_KEY) {
            return window.YANDEX_GEOCODER_API_KEY;
        }
        // Fallback: ключ JavaScript API
        if (window.YANDEX_JAVASCRIPT_API_KEY) {
            return window.YANDEX_JAVASCRIPT_API_KEY;
        }
        // Fallback: data-атрибут модального окна
        if (modal && modal.getAttribute('data-maps-api-key')) {
            return modal.getAttribute('data-maps-api-key');
        }
        // Fallback: legacy переменная
        if (window.YANDEX_MAPS_API_KEY) {
            return window.YANDEX_MAPS_API_KEY;
        }
        return '';
    }

    /* ==================== Яндекс Карта 3.0 ==================== */

    function initYandexMapForPvz() {
        if (!ymaps3 || yamap) return;
        
        var apiKey = getMapApiKey();
        if (!apiKey) {
            var mapUnavailable = document.getElementById('mapUnavailableWarning');
            var mapContainer = document.getElementById('yandexMapContainer');
            if (mapContainer) mapContainer.style.display = 'none';
            if (mapUnavailable) mapUnavailable.style.display = 'block';
            return;
        }

        loadYandexMaps().then(function(ym) {
            initYandexMap();
        }).catch(function(err) {
            console.error('Failed to load Yandex Maps:', err);
            var mapUnavailable = document.getElementById('mapUnavailableWarning');
            var mapContainer = document.getElementById('yandexMapContainer');
            if (mapContainer) mapContainer.style.display = 'none';
            if (mapUnavailable) mapUnavailable.style.display = 'block';
        });
    }

    function initYandexMap() {
        if (!ymaps3) return;
        
        try {
            console.log('🔍 ymaps3 version check...');
            
            var YMap = ymaps3.YMap;
            var YMapDefaultSchemeLayer = ymaps3.YMapDefaultSchemeLayer;
            var YMapDefaultFeaturesLayer = ymaps3.YMapDefaultFeaturesLayer;
            var YMapCollection = ymaps3.YMapCollection;
            var YMapMarker = ymaps3.YMapMarker;
            
            console.log('📦 Checking constructors...');
            console.log('  YMap:', typeof YMap);
            console.log('  YMapDefaultSchemeLayer:', typeof YMapDefaultSchemeLayer);
            console.log('  YMapDefaultFeaturesLayer:', typeof YMapDefaultFeaturesLayer);
            console.log('  YMapCollection:', typeof YMapCollection);
            
            if (!YMap) {
                console.error('❌ YMap constructor not found');
                return;
            }
            
            var mapContainer = document.getElementById('yandexMap');
            if (!mapContainer) {
                console.error('❌ mapContainer not found');
                return;
            }
            
            // Yandex Maps 3.0 API использует Promise-based инициализацию
            // Сначала создаем карту, затем добавляем слои
            
            // Создаем карту
            var map = new YMap(mapContainer, {
                location: {
                    center: currentCenter,
                    zoom: 12
                }
            });
            
            console.log('🗺️ Map created, type:', typeof map);
            
            // Добавляем слои через addChild (Yandex Maps 3.0 API)
            map.addChild(new YMapDefaultSchemeLayer());
            console.log('✅ Scheme layer added');
            
            // YMapDefaultFeaturesLayer требуется для работы маркеров (YMapMarker использует default data source)
            if (YMapDefaultFeaturesLayer) {
                map.addChild(new YMapDefaultFeaturesLayer());
                console.log('✅ Features layer added (required for markers)');
            } else {
                console.warn('⚠️ YMapDefaultFeaturesLayer not available');
            }
            
            // Создаем коллекцию маркеров
            var collection = null;
            if (YMapCollection && typeof YMapCollection === 'function') {
                try {
                    collection = new YMapCollection(mapContainer, {
                        components: 'points'
                    });
                    console.log('📍 Collection created');
                    
                    // Добавляем коллекцию на карту
                    map.addChild(collection);
                } catch(e) {
                    console.warn('⚠️ Failed to create collection:', e);
                }
            }
            
            yamap = {
                map: map,
                collection: collection,
                markers: [],
                components: {
                    YMap: YMap,
                    YMapDefaultSchemeLayer: YMapDefaultSchemeLayer,
                    YMapDefaultFeaturesLayer: YMapDefaultFeaturesLayer,
                    YMapMarker: YMapMarker,
                    YMapCollection: YMapCollection
                }
            };
            
            // Сохраняем глобально для отладки
            window.coffeeShopMap = map;
            window.coffeeShopCollection = collection;
            
            console.log('✅ Map initialization complete');
            
            // Загружаем точки ПВЗ/постоматов
            loadPvzPoints();
        } catch (e) {
            console.error('Yandex Map init error:', e);
        }
    }

    function loadPvzPoints() {
        if (!yamap || !yamap.map) return;
        
        // Удаляем старые маркеры
        pointObjects.forEach(function(obj) {
            try { obj.unlink(); } catch(e) {}
        });
        pointObjects = [];

        // Загружаем точки ПВЗ/постоматов через API
        var type = selectedType; // 'pvz' или 'postomat'
        fetch('/checkout/pvz-locations/?type=' + type + '&city=moscow')
            .then(function(response) { return response.json(); })
            .then(function(data) {
                var points = data.success ? data.points : getMockPvzPoints(type);
                renderPvzPoints(points);
            })
            .catch(function() {
                var points = getMockPvzPoints(type);
                renderPvzPoints(points);
            });
    }

    function renderPvzPoints(points) {
        if (!yamap || !yamap.map) {
            console.error('Map not available');
            return;
        }
        
        // Очищаем старые маркеры через удаление дочерних элементов
        pointObjects.forEach(function(obj) {
            try {
                if (obj && obj.unlink) obj.unlink();
            } catch(e) {}
        });
        pointObjects = [];
        
        var YMapMarker = ymaps3.YMapMarker;
        
        points.forEach(function(point) {
            var coordinates = point.coordinates || point.coords || currentCenter;
            var icon = createPvzIcon(point, selectedType);
            
            try {
                // Создаем маркер напрямую
                var marker = new YMapMarker({
                    coordinates: coordinates,
                    icon: icon
                });
                
                // Добавляем маркер как дочерний элемент карты
                yamap.map.addChild(marker);
                
                // Добавляем обработчик клика
                marker.events.add('click', function() {
                    selectedAddress = point.address || point.name;
                    document.getElementById('yandexAddressInput').value = selectedAddress;
                    selectedType = point.type || selectedType;
                    
                    highlightSelectedPoint({});
                    
                    calculateDelivery();
                });
                
                pointObjects.push(marker);
            } catch(e) {
                console.warn('Failed to add PVZ marker:', e);
            }
        });
    }

    function createPvzIcon(point, type) {
        var iconClass = type === 'pvz' ? '📦' : '📮';
        var bgColor = type === 'pvz' ? '#4CAF50' : '#2196F3';
        
        return '<div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;background:' + 
               bgColor + ';border-radius:50%;font-size:20px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.3);border:2px solid #fff;" ' +
               'title="' + (point.address || point.name) + '">' + iconClass + '</div>';
    }

    function getMockPvzPoints(type) {
        var points = [];
        var pvzPoints = [
            { name: 'ПВЗ Тверская', coordinates: [55.758, 37.608], address: 'Москва, ул. Тверская, 15' },
            { name: 'ПВЗ Арбат', coordinates: [55.749, 37.588], address: 'Москва, ул. Арбат, 10' },
            { name: 'ПВЗ Парк Культуры', coordinates: [55.743, 37.585], address: 'Москва, ул. Большая Ордынка, 21' },
            { name: 'ПВЗ Садовая', coordinates: [55.761, 37.592], address: 'Москва, Садовая-Спасская ул., 19' },
            { name: 'ПВЗ Деловой центр', coordinates: [55.755, 37.535], address: 'Москва, Пресненская наб., 8' }
        ];
        var postomatPoints = [
            { name: 'Постомат Тверская', coordinates: [55.759, 37.610], address: 'Москва, ул. Тверская, 23' },
            { name: 'Постомат Лубянка', coordinates: [55.753, 37.637], address: 'Москва, Лубянская пл., 3' },
            { name: 'Постомат Киевская', coordinates: [55.745, 37.564], address: 'Москва, Киевская пл., 1' }
        ];
        
        return type === 'postomat' ? postomatPoints : pvzPoints;
    }

    function highlightSelectedPoint(marker) {
        // В Yandex Maps 3.0 стилизация маркеров через icon
        // Упрощенная версия - просто сбрасываем все маркеры
        pointObjects = [];
    }

    /* ==================== Шаг 3: Расчёт стоимости ==================== */

    function calculateDelivery() {
        var costEl = document.getElementById('widgetCost');
        var etaEl = document.getElementById('widgetEta');
        var confirmBtn = document.getElementById('confirmDeliveryBtn');

        if (!costEl || !etaEl) return;

        costEl.textContent = 'Расчёт...';
        etaEl.textContent = '';
        if (confirmBtn) confirmBtn.disabled = true;

        var addressValue = selectedAddress || document.getElementById('yandexAddressInput')?.value || '';
        if (!addressValue) return;

        // Парсим адрес
        var address = parseAddress(addressValue);
        address.delivery_type = selectedType;

        fetch('/checkout/calculate-delivery/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify(address),
        })
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.success && data.price) {
                selectedPrice = data.price;
                selectedEta = data.eta || '30-45 мин';
                costEl.textContent = CoffeeShop.formatPrice(data.price) + ' ₽';
                etaEl.textContent = data.eta || '30-45 мин';
                updateConfirmButton();
            } else {
                // Fallback
                selectedPrice = 299;
                selectedEta = '30-45 мин';
                costEl.textContent = '299 ₽';
                etaEl.textContent = '30-45 мин';
                updateConfirmButton();
            }
        })
        .catch(function () {
            // Fallback on error
            selectedPrice = 299;
            selectedEta = '30-45 мин';
            costEl.textContent = '299 ₽';
            etaEl.textContent = '30-45 мин';
            updateConfirmButton();
        });
    }

    function parseAddress(raw) {
        var result = {
            city: '',
            street: '',
            house: '',
            apartment: '',
        };
        var parts = raw.split(',').map(function (s) { return s.trim(); });

        if (parts.length >= 1) {
            result.city = parts[0];
        }
        if (parts.length >= 2) {
            result.street = parts[1];
        }
        if (parts.length >= 3) {
            var parts3 = parts[2].split('-');
            result.house = parts3[0].trim();
            if (parts3.length > 1) {
                result.apartment = parts3[1].trim();
            }
        }

        return result;
    }

    function updateConfirmButton() {
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (!confirmBtn) return;

        confirmBtn.disabled = !(selectedType && selectedAddress && selectedPrice !== null);
    }

    /* ==================== Подтверждение ==================== */

    function confirmDelivery() {
        if (!selectedType || !selectedAddress || selectedPrice === null) {
            return;
        }

        // Заполняем поля на странице оформления
        var addressField = document.getElementById('id_delivery_address');
        var deliveryCostSpan = document.getElementById('deliveryCost');
        var deliveryEtaSpan = document.getElementById('deliveryEta');
        var deliveryInfoBlock = document.getElementById('deliveryInfoBlock');

        if (addressField) {
            addressField.value = selectedAddress;
        }

        if (deliveryCostSpan) {
            deliveryCostSpan.textContent = CoffeeShop.formatPrice(selectedPrice) + ' ₽';
        }

        if (deliveryEtaSpan) {
            deliveryEtaSpan.textContent = selectedEta;
        }

        if (deliveryInfoBlock) {
            deliveryInfoBlock.style.display = 'block';
        }

        // Скрываем старый блок адреса
        var addressBlock = document.getElementById('addressBlock');
        if (addressBlock) {
            addressBlock.style.display = 'none';
        }

        // Закрываем модалку
        closeModal();

        // Показываем уведомление
        if (window.CoffeeShop && CoffeeShop.showToast) {
            CoffeeShop.showToast('Доставка успешно настроена', 'success');
        }
    }

    /* ==================== Утилиты ==================== */

    function resetWidget() {
        selectedType = null;
        selectedAddress = null;
        selectedPrice = null;
        selectedEta = null;
        addressInputHandlerAttached = false;

        // Очистка карты
        pointObjects.forEach(function(obj) {
            try { obj.unlink(); } catch(e) {}
        });
        pointObjects = [];
        yamap = null;

        // Сброс радио-кнопок
        var radios = document.querySelectorAll('input[name="yandex_delivery_type"]');
        radios.forEach(function (r) { r.checked = false; });

        // Сброс поля адреса
        var addressInput = document.getElementById('yandexAddressInput');
        if (addressInput) addressInput.value = '';

        // Скрытие шага 3
        var step3 = document.getElementById('deliveryStep3');
        if (step3) step3.style.display = 'none';

        // Скрытие карты и поля ввода адреса
        var mapContainer = document.getElementById('yandexMapContainer');
        if (mapContainer) mapContainer.style.display = 'none';
        var addressWrap = document.getElementById('yandexAddressInputWrap');
        if (addressWrap) addressWrap.style.display = 'none';
        var mapUnavailable = document.getElementById('mapUnavailableWarning');
        if (mapUnavailable) mapUnavailable.style.display = 'none';

        // Сброс стоимости и ETA
        var costEl = document.getElementById('widgetCost');
        var etaEl = document.getElementById('widgetEta');
        if (costEl) costEl.textContent = 'Расчёт...';
        if (etaEl) etaEl.textContent = '';

        // Отключение кнопки подтверждения
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (confirmBtn) confirmBtn.disabled = true;

        // Скрытие списка автокомплита
        var list = document.getElementById('yandexAutocompleteList');
        if (list) {
            list.style.display = 'none';
            list.innerHTML = '';
        }

        // Очистка timeout автокомплита
        if (addressAutocompleteTimeout) {
            clearTimeout(addressAutocompleteTimeout);
            addressAutocompleteTimeout = null;
        }

        // Удаление обработчика autocomplete
        var addressInput = document.getElementById('yandexAddressInput');
        if (addressInput && addressInput._autocompleteHandler) {
            addressInput.removeEventListener('input', addressInput._autocompleteHandler);
            addressInput._autocompleteHandler = null;
        }
    }

    function showAuthPrompt() {
        // Эта функция больше не вызывается — виджет открывается всегда
        console.log('YandexDeliveryWidget: showAuthPrompt called but modal opens anyway');
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
        init: init,
        openModal: openModal,
    };

})();

// Не используем DOMContentLoaded — скрипт загружается в конце body,
// но bootstrap может не быть готов к моменту инициализации
// Инициализация происходит принудительно в checkout.html

