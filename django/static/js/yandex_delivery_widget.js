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
    var ymap = null; // Ссылка на объект YMap
    var ymapContainer = null; // DOM-контейнер для пересоздания карты
    var ymapMapElement = null; // DOM-элемент карты (div#yandexMap)
    var pointObjects = [];
    var selectedPoint = null;
    var currentCenter = [50.1016, 53.1949];  // Самара: [долгота, широта]
    var currentZoom = 12; // Текущий зум

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
            // Инициализируем карту после того как модалка открылась (контейнер видим)
            setTimeout(function() {
                if (selectedType && selectedType !== 'courier') {
                    initYandexMapForPvz();
                }
            }, 100);
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

        // Инициализируем карту для ПВЗ/Постомат
        if (selectedType && selectedType !== 'courier') {
            setTimeout(function() {
                initYandexMapForPvz();
            }, 100);
        }

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

                        if (ymap) {
                            // Если есть координаты из геокодера - используем их
                            // API Яндекса возвращает [долгота, широта]
                            if (coords) {
                                currentCenter = [parseFloat(coords[0]), parseFloat(coords[1])];
                                setMapCenter(parseFloat(coords[0]), parseFloat(coords[1]), 16);
                                placeSingleMarker(currentCenter, text);
                            } else {
                                // Иначе геокодируем адрес и центрируем карту
                                geocodeAddressAndCenterMap(text);
                            }
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
        if (!ymap) {
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
        
        console.log('📍 Creating single marker at:', coords);
        
        var icon = '<div style="width:30px;height:30px;background:#FF6B6B;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.3);">📍</div>';
        
        try {
            var YMapMarker = ymaps3.YMapMarker;
            var marker = new YMapMarker({
                coordinates: coords,
                icon: icon,
                onClick: function() {
                    console.log('📍 Marker clicked:', text);
                    selectedAddress = text;
                    document.getElementById('yandexAddressInput').value = text;
                    calculateDelivery();
                }
            });
            
            console.log('✅ Marker created, adding to map...');
            ymap.addChild(marker);
            pointObjects.push(marker);
            console.log('✅ Marker added successfully');
        } catch(e) {
            console.error('❌ Failed to add single marker:', e);
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

    /* ==================== Геокодирование адреса ==================== */

    function geocodeAddress(address) {
        return new Promise(function(resolve) {
            geocodeViaApi(address, function(coords) {
                if (coords) {
                    resolve(coords);
                } else {
                    // Fallback на центр Самары [долгота, широта]
                    resolve([50.1016, 53.1949]);
                }
            });
        });
    }

    function geocodeViaApi(address, callback) {
        // Прокси запрос к Django backend для геокодирования
        fetch('/checkout/geocode-address/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            },
            body: JSON.stringify({ query: address }),
        })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success && data.features && data.features.length > 0) {
                var first = data.features[0];
                if (first.coords) {
                    // API Яндекса возвращает [долгота, широта]
                    var lon = parseFloat(first.coords[0]);
                    var lat = parseFloat(first.coords[1]);
                    console.log('✅ Geocoded address:', address, '->', [lon, lat]);
                    callback([lon, lat]);
                } else {
                    callback(null);
                }
            } else {
                callback(null);
            }
        })
        .catch(function(err) {
            console.error('❌ Geocode error:', err);
            callback(null);
        });
    }

    /**
     * Обратное геокодирование: координаты → адрес.
     * Вызывается при клике на карту.
     */
    function reverseGeocodeToAddress(lon, lat) {
        var coordsString = lon.toFixed(6) + ',' + lat.toFixed(6);
        console.log('📡 Reverse geocoding:', coordsString);
        
        var csrfToken = getCookie('csrftoken');
        console.log('🔑 CSRF token:', csrfToken ? 'present' : 'missing');
        
        fetch('/checkout/geocode-address/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken || '',
            },
            body: JSON.stringify({ query: coordsString }),
        })
        .then(function(response) {
            console.log('📡 Geocode proxy response status:', response.status);
            return response.json();
        })
        .then(function(data) {
            console.log('📦 Geocode proxy data:', data);
            var addressInput = document.getElementById('yandexAddressInput');
            console.log('🔍 Address input element:', addressInput);
            
            if (data.success && data.features && data.features.length > 0) {
                var first = data.features[0];
                var address = first.text || 'Выбранный адрес';
                var coords = first.coords || [lon, lat];
                
                console.log('✅ Reverse geocoded:', coordsString, '->', address);
                
                // Обновляем поисковую строку реальным адресом
                if (addressInput) {
                    console.log('✏️ Setting address input value to:', address);
                    addressInput.value = address;
                    console.log('✅ Address input value set to:', addressInput.value);
                } else {
                    console.error('❌ Address input element not found!');
                }
                
                selectedAddress = address;
                
                // Ставим маркер на геокодированные координаты
                placeSingleMarker([parseFloat(coords[0]), parseFloat(coords[1])], address);
                
                // Пересчитываем доставку
                calculateDelivery();
            } else {
                console.warn('⚠️ No address found for:', coordsString);
                if (addressInput) {
                    addressInput.value = 'Адрес не найден';
                }
                placeSingleMarker([lon, lat], 'Выбранная точка');
            }
        })
        .catch(function(err) {
            console.error('❌ Reverse geocode error:', err);
            var addressInput = document.getElementById('yandexAddressInput');
            if (addressInput) {
                addressInput.value = 'Ошибка геокодирования';
            }
            placeSingleMarker([lon, lat], 'Выбранная точка');
        });
    }

    /**
     * Геокодирует адрес и центрирует карту по найденным координатам.
     * Вызывается при выборе адреса из автокомплита.
     */
    function geocodeAddressAndCenterMap(address) {
        geocodeViaApi(address, function(coords) {
            if (coords && ymap) {
                currentCenter = coords;
                setMapCenter(coords[0], coords[1], 16);
                placeSingleMarker(coords, address);
                console.log('✅ Map centered on:', address, 'at', coords);
            } else if (ymap) {
                currentCenter = [50.1016, 53.1949];
                setMapCenter(50.1016, 53.1949, 14);
                placeSingleMarker(currentCenter, address);
                console.log('⚠️ Using fallback center for:', address);
            }
        });
    }

    /* ==================== Яндекс Карта 3.0 ==================== */

    function initYandexMapForPvz() {
        if (ymap) return; // Карта уже инициализирована
        
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

    /* ==================== Кастомные контролы зума ==================== */
    
    function createMap(center, zoom) {
        if (!ymaps3) return null;
        
        var YMap = ymaps3.YMap;
        var YMapDefaultSchemeLayer = ymaps3.YMapDefaultSchemeLayer;
        var YMapDefaultFeaturesLayer = ymaps3.YMapDefaultFeaturesLayer;
        var YMapCollection = ymaps3.YMapCollection;
        var YMapMarker = ymaps3.YMapMarker;
        var YMapScaleControl = ymaps3.YMapScaleControl;
        
        var mapElement = document.getElementById('yandexMap');
        if (!mapElement) return null;
        
        // Запоминаем DOM-элемент карты для обработчика клика
        ymapMapElement = mapElement;
        console.log('🗺️ Map DOM element captured:', ymapMapElement);
        
        // YMaps 3.0: events указываются в опциях при создании карты
        var mapOptions = {
            location: {
                center: center,
                zoom: zoom
            },
            events: ['click'] // Обязательно: включаем поддержку событий клика
        };
        
        var map = new YMap(mapElement, mapOptions);
        
        map.addChild(new YMapDefaultSchemeLayer());
        if (YMapDefaultFeaturesLayer) {
            map.addChild(new YMapDefaultFeaturesLayer());
        }
        
        var collection = null;
        if (YMapCollection && typeof YMapCollection === 'function') {
            try {
                collection = new YMapCollection(mapElement, {
                    components: 'points'
                });
                map.addChild(collection);
            } catch(e) {
                console.warn('⚠️ Failed to create collection:', e);
            }
        }
        
        if (YMapScaleControl) {
            try {
                var scaleControl = new YMapScaleControl();
                map.addChild(scaleControl);
            } catch(e) {
                console.warn('⚠️ Failed to add scale control:', e);
            }
        }
        
        return { map: map, collection: collection, components: { YMap: YMap, YMapDefaultSchemeLayer: YMapDefaultSchemeLayer, YMapDefaultFeaturesLayer: YMapDefaultFeaturesLayer, YMapMarker: YMapMarker, YMapCollection: YMapCollection, YMapScaleControl: YMapScaleControl } };
    }
    
    function addHtmlZoomControls(container, map) {
        // Создаем HTML контролы для зума
        var zoomContainer = document.createElement('div');
        zoomContainer.style.cssText = 'position:absolute;top:10px;right:10px;display:flex;flex-direction:column;gap:5px;z-index:100;';
        
        // Кнопка +
        var btnPlus = document.createElement('button');
        btnPlus.innerHTML = '+';
        btnPlus.style.cssText = 'width:36px;height:36px;font-size:20px;font-weight:bold;border:2px solid #ccc;border-radius:6px;background:#fff;cursor:pointer;box-shadow:0 2px 4px rgba(0,0,0,0.2);';
        btnPlus.addEventListener('click', function() {
            var z = currentZoom;
            if (z < 18) {
                setMapCenterWithZoom(z + 1);
            }
        });
        
        // Кнопка -
        var btnMinus = document.createElement('button');
        btnMinus.innerHTML = '−';
        btnMinus.style.cssText = 'width:36px;height:36px;font-size:20px;font-weight:bold;border:2px solid #ccc;border-radius:6px;background:#fff;cursor:pointer;box-shadow:0 2px 4px rgba(0,0,0,0.2);';
        btnMinus.addEventListener('click', function() {
            var z = currentZoom;
            if (z > 3) {
                setMapCenterWithZoom(z - 1);
            }
        });
        
        zoomContainer.appendChild(btnPlus);
        zoomContainer.appendChild(btnMinus);
        container.appendChild(zoomContainer);
        
        console.log('✅ HTML zoom controls added');
    }
    
    function setMapCenterWithZoom(newZoom) {
        try {
            currentZoom = newZoom;
            if (yamap) yamap.zoom = newZoom;
            
            console.log('🔍 Zooming with center:', currentCenter, 'zoom:', newZoom);
            ymap.setLocation({
                center: currentCenter,
                zoom: newZoom
            });
            console.log('✅ Zoom set via currentCenter');
        } catch(e) {
            console.error('❌ Failed to set zoom:', e);
        }
    }

    function setMapCenter(lat, lon, zoom) {
        try {
            currentCenter = [lat, lon];
            currentZoom = zoom;
            if (yamap) yamap.zoom = zoom;
            console.log('🔄 Setting center to', [lat, lon], 'zoom', zoom);
            
            ymap.setLocation({
                center: [lat, lon],
                zoom: zoom
            });
            
            console.log('✅ Center set via setLocation');
        } catch(e) {
            console.error('❌ Failed to set map center:', e);
        }
    }
    
    function getMapCenter() {
        if (ymap && ymap.location) {
            return ymap.location.center;
        }
        return currentCenter;
    }
    
    // Ищет location объекта YMap через рефлексию (проходит по прототипам)
    // Возвращает { center: [lon, lat], zoom: number } или null
    function _findMapLocation(map) {
        var seen = new WeakSet();
        var obj = map;
        while (obj && obj !== Object.prototype) {
            seen.add(obj);
            var props = Object.getOwnPropertyNames(obj);
            for (var i = 0; i < props.length; i++) {
                try {
                    var propName = props[i];
                    var descriptor = Object.getOwnPropertyDescriptor(obj, propName);
                    var val = null;
                    
                    if (descriptor) {
                        // Если есть getter - вызываем его
                        if (descriptor.get) {
                            val = descriptor.get.call(map);
                        } else if (descriptor.value !== undefined) {
                            val = descriptor.value;
                        }
                    }
                    
                    if (val && typeof val === 'object') {
                        if (Array.isArray(val.center) && val.center.length === 2 && val.zoom !== undefined) {
                            console.log('🔍 Found location at:', propName, val);
                            return val;
                        }
                        // Проверяем вложенные объекты
                        var inner = _findMapLocation(val);
                        if (inner) return inner;
                    }
                } catch(e) {}
            }
            obj = Object.getPrototypeOf(obj);
        }
        return null;
    }
    
    function reRenderMarkers() {
        // Перемещаем существующие маркеры на новую карту
        pointObjects.forEach(function(obj) {
            try {
                if (obj && ymap) {
                    ymap.addChild(obj);
                }
            } catch(e) {}
        });
    }

    function initYandexMap() {
        if (!ymaps3) return;
        if (ymap) return; // Карта уже инициализирована
        
        try {
            console.log('🔍 ymaps3 keys:', Object.keys(ymaps3));
            
            var YMap = ymaps3.YMap;
            var YMapDefaultSchemeLayer = ymaps3.YMapDefaultSchemeLayer;
            var YMapDefaultFeaturesLayer = ymaps3.YMapDefaultFeaturesLayer;
            var YMapCollection = ymaps3.YMapCollection;
            var YMapMarker = ymaps3.YMapMarker;
            var YMapScaleControl = ymaps3.YMapScaleControl;
            
            console.log('📦 Checking controls...');
            console.log('  YMap:', typeof YMap);
            console.log('  YMapScaleControl:', typeof YMapScaleControl);
            
            if (!YMap) {
                console.error('❌ YMap constructor not found');
                return;
            }
            
            var mapContainer = document.getElementById('yandexMap');
            if (!mapContainer) {
                console.error('❌ mapContainer not found');
                return;
            }
            
            // Создаем карту с центром в Самаре
            // Yandex Maps 3.0 использует порядок [долгота, широта]
            console.log('🗺️ Creating Yandex Map with Samara center [50.1016, 53.1949]...');
            var result = createMap([50.1016, 53.1949], 12);
            if (!result) {
                console.error('❌ Failed to create map');
                return;
            }
            
            ymap = result.map;
            yamap = {
                map: result.map,
                collection: result.collection,
                markers: [],
                zoom: 12,
                components: result.components
            };
            mapInstance = result.map;
            
            console.log('✅ Map created with createMap helper');
            
            // Инициализируем currentCenter из начальной позиции карты
            if (ymap.location) {
                currentCenter = ymap.location.center;
                currentZoom = ymap.location.zoom;
                console.log('🔍 Initial center:', currentCenter, 'zoom:', currentZoom);
            }
            
            console.log('✅ Map initialization complete');
            
            // ========================================
            // Обработчик клика по карте для YMaps 3.0
            // ========================================
            // В YMaps 3 координаты приходят прямо через e.coord в событии клика
            
            function handleMapClick(e) {
                console.log('🗺️ Click event triggered');
                console.log('  e.coord:', e.coord);
                
                // e.coord — это [долгота, широта] в формате EPSG:3857
                if (!e.coord || !Array.isArray(e.coord) || e.coord.length < 2) {
                    console.error('❌ Invalid e.coord:', e.coord);
                    return;
                }
                
                var lon = e.coord[0];
                var lat = e.coord[1];
                console.log('  📍 Click at: lon=' + lon + ', lat=' + lat);
                
                // Центрируем карту на точку клика
                setMapCenter(lon, lat, currentZoom);
                
                // Обратное геокодирование: координаты → адрес для поисковой строки
                reverseGeocodeToAddress(lon, lat);
            }
            
            // YMaps 3.0: events добавляются через опции при создании карты
            if (ymap.events && typeof ymap.events.add === 'function') {
                ymap.events.add('click', handleMapClick);
                console.log('✅ Click handler registered via ymap.events.add');
            } else {
                console.warn('⚠️ ymap.events.add not available, using DOM fallback');
                if (ymapMapElement) {
                    ymapMapElement.addEventListener('click', function(domEvent) {
                        // Получаем центр карты
                        var center = ymap.location.center;
                        var zoom = ymap.location.zoom;
                        
                        // Получаем размеры карты
                        var rect = ymapMapElement.getBoundingClientRect();
                        var x = domEvent.clientX - rect.left;
                        var y = domEvent.clientY - rect.top;
                        var centerX = rect.width / 2;
                        var centerY = rect.height / 2;
                        
                        // Конвертируем пиксели в координаты (EPSG:3857)
                        var metersPerPixel = 156543.03392804095 * Math.cos(center[1] * Math.PI / 180) / Math.pow(2, zoom);
                        var pixelScale = 256; // размер тайла
                        
                        var lon = center[0] + (x - centerX) * metersPerPixel / 111320;
                        var lat = center[1] - (y - centerY) * metersPerPixel / 111320;
                        
                        console.log('🗺️ DOM click converted to coords:', [lon, lat]);
                        
                        setMapCenter(lon, lat, zoom);
                        reverseGeocodeToAddress(lon, lat);
                    });
                    console.log('✅ DOM click fallback registered on map element');
                }
            }
            
            // Добавляем кастомные контролы зума
            setTimeout(function() {
                addHtmlZoomControls(mapContainer, result.map);
            }, 500);
            
            // Подписываемся на изменение позиции карты для синхронизации currentCenter
            try {
                ymap.subscribe('update', function() {
                    if (ymap.location && ymap.location.center) {
                        currentCenter = ymap.location.center;
                        currentZoom = ymap.location.zoom;
                    }
                });
                console.log('✅ Map update subscription added');
            } catch(e) {
                console.warn('⚠️ Failed to add update subscription:', e);
            }
            
            // Загружаем точки ПВЗ/постоматов
            loadPvzPoints();
        } catch (e) {
            console.error('Yandex Map init error:', e);
        }
    }

    function loadPvzPoints() {
        if (!ymap) return;
        
        // Удаляем старые маркеры
        pointObjects.forEach(function(obj) {
            try { obj.unlink(); } catch(e) {}
        });
        pointObjects = [];

        // Загружаем точки ПВЗ/постоматов через API
        var type = selectedType; // 'pvz' или 'postomat'
        fetch('/checkout/pvz-locations/?type=' + type)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                console.log('📍 API response:', data);
                var points = data.points || [];
                if (points.length === 0 && data.error) {
                    console.warn('⚠️ No PVZ points found:', data.error);
                }
                renderPvzPoints(points);
            })
            .catch(function(err) {
                console.error('❌ Failed to load PVZ points:', err);
                renderPvzPoints([]);
            });
    }


    function renderPvzPoints(points) {
        if (!ymap) {
            console.error('Map not available');
            return;
        }
        
        console.log('📍 Rendering', points.length, 'PVZ points');
        
        // Очищаем старые маркеры через удаление дочерних элементов
        pointObjects.forEach(function(obj) {
            try {
                if (obj && obj.unlink) obj.unlink();
            } catch(e) {}
        });
        pointObjects = [];
        
        var YMapMarker = ymaps3.YMapMarker;
        console.log('📍 YMapMarker available:', !!YMapMarker);
        
        points.forEach(function(point, index) {
            var coordinates = point.coordinates || point.coords || currentCenter;
            console.log('📍 Point', index, ':', point.name, 'Coords:', coordinates);
            var icon = createPvzIcon(point, selectedType);
            
            try {
                // Создаем маркер с обработчиком клика
                var marker = new YMapMarker({
                    coordinates: coordinates,
                    icon: icon,
                    onClick: function() {
                        console.log('📍 PVZ marker clicked:', point.name);
                        
                        // Центрируем карту на выбранный ПВЗ
                        if (ymap) {
                            setMapCenter(coordinates[0], coordinates[1], 16);
                        }
                        
                        selectedAddress = point.address || point.name;
                        document.getElementById('yandexAddressInput').value = selectedAddress;
                        selectedType = point.type || selectedType;
                        
                        highlightSelectedPoint({});
                        
                        calculateDelivery();
                    }
                });
                
                console.log('✅ Marker', index, 'created, adding to map...');
                // Добавляем маркер как дочерний элемент карты
                ymap.addChild(marker);
                
                pointObjects.push(marker);
                console.log('✅ Marker', index, 'added successfully');
            } catch(e) {
                console.error('❌ Failed to add PVZ marker:', e);
            }
        });
        
        console.log('✅ All', pointObjects.length, 'markers rendered');
    }

    function createPvzIcon(point, type) {
        var iconClass = type === 'pvz' ? '📦' : '📮';
        var bgColor = type === 'pvz' ? '#4CAF50' : '#2196F3';
        
        var icon = '<div style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;background:' + 
               bgColor + ';border-radius:50%;font-size:20px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.3);border:2px solid #fff;" ' +
               'title="' + (point.address || point.name) + '">' + iconClass + '</div>';
        
        console.log('🎨 Created icon HTML:', icon.substring(0, 50));
        return icon;
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
        ymap = null;
        currentCenter = [50.1016, 53.1949];
        currentZoom = 12;

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

