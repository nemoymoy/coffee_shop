/**
 * Coffee Shop — Yandex Delivery Widget.
 * Модальный виджет выбора доставки через Яндекс Доставку:
 * 1. Выбор типа доставки (курьер / ПВЗ / постомат)
 * 2. Ввод адреса с autocomplete через Яндекс Карты API
 * 3. Расчёт стоимости и ETA
 * 4. Возврат данных на страницу оформления заказа
 */
var YandexDeliveryWidget = (function () {

    /* ==================== State & Constants ==================== */

    var state = {
        modal: null,
        bootstrapModal: null,
        selectedType: null,
        selectedAddress: null,
        selectedPrice: null,
        selectedEta: null,
        ymaps3: null,
        map: null,
        markerCollection: null,
        markers: [],
        currentCenter: [50.1016, 53.1949],
        currentZoom: 12,
        autocompleteTimeout: null,
        mapClickHandler: null,
        lastAutocompleteTime: 0,
        widgetInitialized: false
    };

    var MAP_CENTER = [50.1016, 53.1949];
    var MAP_DEFAULT_ZOOM = 12;
    var MAP_MAX_ZOOM = 18;
    var MAP_MIN_ZOOM = 3;
    var GEOCODER_THROTTLE_MS = 1500;
    var GEOCODER_DEBOUNCE_MS = 800;
    var YMAPS_LOAD_TIMEOUT_MS = 10000;

    /* ==================== Helpers ==================== */

    // Base64 PNG-иконки — загружаются напрямую как картинки, минуя DOM и canvas
    // ymaps3 конвертирует их в WebGL-текстуры без texSubImage(y-flip)
    var ICON_DELIVERY = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAYAAAA7MK6iAAAA4UlEQVR4nOWXzRGEIAyFX3b2aCmWZAEeLMeDhXiwEPthL47DT4LJLsjO+I4Q8iUBJQCNRNYFzjknOiNS+1MZ5mDfBnEJTqDTJBvPsxouTgTAHEwRBBfAqwo0WsdtVQIuAlXA2YyLQC/8BOAzqlLQCO5nfYKrQQW4XOrKagYm4IYy+zq+72YZv03WfQ+MIz+378CyVAIDwLoC2xaOdR0wDCY3zzvVbcHntRXdp8V1+CعيمipgRvK7ZU5AFeFR9AEzBmXgsZimz2x/bH+MjMNX7Mu8//66ixcoZ9fEpYgLG+nDyercYHg0FYoAAAAAElFTkSuQmCC';
    var ICON_PVZ = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAYAAACM/rhtAAABLklEQVR4nO2YMQ7CMAxFfxALM9yJCQnOwMClkDgCSGwcqQdgDVNKSJ3ErUnqSH0rjf36XUExoBwjLWCttdkmxkzuM+kgRyracKTsqIspscPjlD33PN6HjZmibEFfjiMVw5flSGYv+JdYCFd0lSpSSi6sl3qmo4Il5ai6MUlSsIYcVZ+STI64tBynz0DQ3UUtOYfrF6b4IziXnIOSTI5YA73g3Ok5whTbSVArBtAzXh/3U6g+wbXkMPUaRSGZjEgQAM6vC7p3R36222xx219F9dWPeBGUsghKWQHf/wTcr43SOA9jjGkjQc30glrG7I8XaClBYP4Uw/QAIsG5JCk5IDPiWpKpPqSgfxelJXM7mmiCNSQ5CyTRdkvywsrdbrW/H/RRvWH1Ubujpii95f8AR2GnRNYVEz4AAAAASUVORK5CYII=';
    var ICON_POSTOMAT = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAYAAACM/rhtAAABLUlEQVR4nO2YsRHCMAxFv3J0ZABqBmETBmAiFmAWxqBiAzhKQuVgHNlWIuwod3ktsfTylYMgwDikLdB1XZdtQjS5z6SDEqlow5Gyoy7mxPbnZ/bc7dQOGwtFxYK+nEQqhi8rkcxe8C+xEKlokypSSi6sl3qmo4Il5bi6MUlWsIYcV5+TTI64tJykz0DQ3UUtOYfrF6b4IziXnIOTTI7YAr3g3Ok5whSXk6BVCLAzXh/3U2g+wY3mMPcaxaGZjEoQAA6XF+6PN/vZriVcj1tVffMjXgW1rIJaGuD7n0D6tVEa50FEtIwELdMLWhmzP15gSQkC86cYpgcwCc4lyckBmRHXkkz1YQX9uygtmdvRRBOsISlZIKm2W5oXVul2a/n7QR/TG1YfsztqjtJb/g95RadE4ABDdwAAAABJRU5ErkJggg=';

    function getMarkerIcon(type) {
        if (type === 'pvz') return ICON_PVZ;
        if (type === 'postomat') return ICON_POSTOMAT;
        return ICON_DELIVERY; // courier
    }

    /* ==================== Init ==================== */

    function init() {
        state.modal = document.getElementById('deliveryModal');
        if (!state.modal) {
            console.error('[YDW] modal #deliveryModal not found');
            return;
        }

        if (typeof bootstrap === 'undefined') {
            console.error('[YDW] bootstrap is not loaded');
            return;
        }

        try {
            state.bootstrapModal = new bootstrap.Modal(state.modal);
        } catch (e) {
            console.error('[YDW] failed to init modal:', e);
            return;
        }

        state.widgetInitialized = true;
        bindEvents();
    }

    /* ==================== API ==================== */

    function getMapsApiKey() {
        if (window.YANDEX_JAVASCRIPT_API_KEY) return window.YANDEX_JAVASCRIPT_API_KEY;
        if (window.YANDEX_MAPS_API_KEY) return window.YANDEX_MAPS_API_KEY;
        if (state.modal && state.modal.getAttribute('data-maps-api-key')) {
            return state.modal.getAttribute('data-maps-api-key');
        }
        return '';
    }

    function loadYandexMaps() {
        var apiKey = getMapsApiKey();
        if (!apiKey) {
            console.warn('[YDW] No maps API key found');
            return Promise.reject(new Error('No API key'));
        }

        if (typeof ymaps3 !== 'undefined') {
            state.ymaps3 = ymaps3;
            return Promise.resolve(ymaps3);
        }

        return new Promise(function(resolve, reject) {
            var timeout = setTimeout(function() {
                reject(new Error('ymaps3 load timed out'));
            }, YMAPS_LOAD_TIMEOUT_MS);

            var script = document.createElement('script');
            script.src = 'https://api-maps.yandex.ru/3.0/?apikey=' + apiKey + '&lang=ru_RU';
            script.async = true;

            script.onload = function() {
                clearTimeout(timeout);
                try {
                    ymaps3.ready(function() {
                        state.ymaps3 = ymaps3;
                        resolve(ymaps3);
                    });
                } catch (e) {
                    reject(new Error('ymaps3.ready failed'));
                }
            };

            script.onerror = function() {
                clearTimeout(timeout);
                reject(new Error('Failed to load Yandex Maps script'));
            };

            document.head.appendChild(script);
        });
    }

    function apiFetch(url, data) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CoffeeShop.getCookie('csrftoken')
            },
            body: JSON.stringify(data)
        });
    }

    /* ==================== Events ==================== */

    function bindEvents() {
        var openBtn = document.getElementById('openDeliveryModal');
        if (openBtn) {
            openBtn.addEventListener('click', function(e) {
                e.preventDefault();
                openModal();
            });
        } else {
            console.warn('[YDW] button #openDeliveryModal not found');
        }

        var deliveryTypeRadios = document.querySelectorAll('input[name="yandex_delivery_type"]');
        deliveryTypeRadios.forEach(function(radio) {
            radio.addEventListener('change', handleTypeChange);
        });

        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', confirmDelivery);
        }

        state.modal.addEventListener('hidden.bs.modal', function() {
            resetWidget();
        });

        state.modal.addEventListener('shown.bs.modal', function() {
            initAddressAutocomplete();
            if (state.selectedType && state.selectedType !== 'courier') {
                setTimeout(function() {
                    initYandexMapForPvz();
                }, 100);
            }
        });
    }

    function openModal() {
        resetWidget();

        if (state.bootstrapModal) {
            state.bootstrapModal.show();
        } else {
            console.error('[YDW] bootstrapModal is null');
        }
    }

    function closeModal() {
        if (state.bootstrapModal) {
            state.bootstrapModal.hide();
        }
    }

    /* ==================== UI ==================== */

    function handleTypeChange(e) {
        state.selectedType = e.target.value;
        updateStepVisibility();

        if (state.selectedType && state.selectedType !== 'courier') {
            setTimeout(function() {
                initYandexMapForPvz();
            }, 100);
        }

        if (state.selectedAddress) {
            calculateDelivery();
        }

        updateConfirmButton();
    }

    function updateStepVisibility() {
        var step2 = document.getElementById('deliveryStep2');
        var step3 = document.getElementById('deliveryStep3');
        var mapContainer = document.getElementById('yandexMapContainer');
        var addressWrap = document.getElementById('yandexAddressInputWrap');
        var mapUnavailable = document.getElementById('mapUnavailableWarning');

        if (step2) step2.style.display = 'block';

        if (state.selectedType === 'courier') {
            if (mapContainer) mapContainer.style.display = 'none';
            if (addressWrap) addressWrap.style.display = 'block';
            if (mapUnavailable) mapUnavailable.style.display = 'none';
        } else {
            if (mapContainer) mapContainer.style.display = 'block';
            if (addressWrap) addressWrap.style.display = 'block';
            if (mapUnavailable) mapUnavailable.style.display = 'none';
        }

        if (step3) {
            step3.style.display = state.selectedAddress ? 'block' : 'none';
        }
    }

    function updateConfirmButton() {
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (!confirmBtn) return;
        confirmBtn.disabled = !(state.selectedType && state.selectedAddress && state.selectedPrice !== null);
    }

    /* ==================== Geocoder ==================== */

    function initAddressAutocomplete() {
        var input = document.getElementById('yandexAddressInput');
        if (!input) return;

        if (input._autocompleteHandler) {
            input.removeEventListener('input', input._autocompleteHandler);
        }

        input._autocompleteHandler = function() {
            if (state.autocompleteTimeout) {
                clearTimeout(state.autocompleteTimeout);
            }

            var query = input.value.trim();
            var list = document.getElementById('yandexAutocompleteList');
            if (!list) return;

            if (query.length === 0) {
                list.style.display = 'none';
                list.innerHTML = '';
                return;
            }

            state.autocompleteTimeout = setTimeout(function() {
                var now = Date.now();
                var timeSinceLastRequest = now - state.lastAutocompleteTime;

                if (timeSinceLastRequest < GEOCODER_THROTTLE_MS) {
                    var waitTime = GEOCODER_THROTTLE_MS - timeSinceLastRequest;
                    setTimeout(function() {
                        doAutocomplete(query);
                    }, waitTime);
                } else {
                    doAutocomplete(query);
                }
            }, GEOCODER_DEBOUNCE_MS);
        };

        input.addEventListener('input', input._autocompleteHandler);
    }

    function doAutocomplete(query) {
        var list = document.getElementById('yandexAutocompleteList');
        var input = document.getElementById('yandexAddressInput');
        if (!list || !input) return;

        list.innerHTML = '';

        apiFetch('/checkout/geocode-address/', { query: query })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            list.innerHTML = '';
            state.lastAutocompleteTime = Date.now();

            if (data.success && data.features && data.features.length > 0) {
                var features = data.features;

                features.forEach(function(item) {
                    var text = item.text;
                    var coords = item.coords;

                    if (!text) return;

                    var itemEl = document.createElement('div');
                    itemEl.className = 'autocomplete-item';
                    itemEl.textContent = text;

                    itemEl.addEventListener('click', function() {
                        input.value = text;
                        list.style.display = 'none';
                        state.selectedAddress = text;

                        if (state.map) {
                            if (coords) {
                                state.currentCenter = [parseFloat(coords[0]), parseFloat(coords[1])];
                                setMapCenter(parseFloat(coords[0]), parseFloat(coords[1]), 16);
                                placeSingleMarker(state.currentCenter, text);
                            } else {
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
                    list.innerHTML = '<div class="autocomplete-item text-warning">Nothing found</div>';
                    list.style.display = 'block';
                }
            } else if (data.error) {
                list.innerHTML = '<div class="autocomplete-item text-warning">Warning: ' + data.error + '</div>';
                list.style.display = 'block';
            } else {
                list.innerHTML = '<div class="autocomplete-item text-warning">Nothing found</div>';
                list.style.display = 'block';
            }
        })
        .catch(function(err) {
            console.error('[YDW] Geocoder proxy error:', err);
            list.innerHTML = '<div class="autocomplete-item text-danger">Connection error</div>';
            list.style.display = 'block';
        });
    }

    function placeSingleMarker(coords, text) {
        if (!state.map || !state.ymaps3) return;

        clearMarkers();

        var YMapMarker = state.ymaps3.YMapMarker;
        if (!YMapMarker) return;

        var icon = ICON_DELIVERY;

        try {
            var marker = new YMapMarker({
                coordinates: coords,
                icon: icon,
                onClick: function() {
                    state.selectedAddress = text;
                    document.getElementById('yandexAddressInput').value = text;
                    calculateDelivery();
                }
            });

            state.map.addChild(marker);
            state.markers.push(marker);
        } catch(e) {
            console.error('[YDW] Failed to add single marker:', e);
        }
    }

    function clearMarkers() {
        state.markers.forEach(function(obj) {
            try {
                if (obj && obj.unlink) obj.unlink();
            } catch(e) {}
        });
        state.markers = [];
    }

    /* ==================== Geocoder (continued) ==================== */

    function geocodeViaApi(address, callback) {
        apiFetch('/checkout/geocode-address/', { query: address })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success && data.features && data.features.length > 0) {
                var first = data.features[0];
                if (first.coords) {
                    var lon = parseFloat(first.coords[0]);
                    var lat = parseFloat(first.coords[1]);
                    console.log('[YDW] Geocoded:', address, '->', [lon, lat]);
                    callback([lon, lat]);
                } else {
                    callback(null);
                }
            } else {
                callback(null);
            }
        })
        .catch(function(err) {
            console.error('[YDW] Geocode error:', err);
            callback(null);
        });
    }

    function geocodeAddress(address) {
        return new Promise(function(resolve) {
            geocodeViaApi(address, function(coords) {
                if (coords) {
                    resolve(coords);
                } else {
                    resolve([50.1016, 53.1949]);
                }
            });
        });
    }

    function reverseGeocodeToAddress(lon, lat) {
        var coordsString = lon.toFixed(6) + ',' + lat.toFixed(6);

        apiFetch('/checkout/geocode-address/', { query: coordsString })
        .then(function(response) { return response.json(); })
        .then(function(data) {
            var addressInput = document.getElementById('yandexAddressInput');

            if (data.success && data.features && data.features.length > 0) {
                var first = data.features[0];
                var address = first.text || 'Selected address';
                var coords = first.coords || [lon, lat];

                if (addressInput) {
                    addressInput.value = address;
                }

                state.selectedAddress = address;
                placeSingleMarker([parseFloat(coords[0]), parseFloat(coords[1])], address);
                calculateDelivery();
            } else {
                if (addressInput) {
                    addressInput.value = 'Address not found';
                }
                placeSingleMarker([lon, lat], 'Selected point');
            }
        })
        .catch(function(err) {
            console.error('[YDW] Reverse geocode error:', err);
            var addressInput = document.getElementById('yandexAddressInput');
            if (addressInput) {
                addressInput.value = 'Geocoding error';
            }
            placeSingleMarker([lon, lat], 'Selected point');
        });
    }

    function geocodeAddressAndCenterMap(address) {
        geocodeViaApi(address, function(coords) {
            if (coords && state.map) {
                state.currentCenter = coords;
                setMapCenter(coords[0], coords[1], 16);
                placeSingleMarker(coords, address);
            } else if (state.map) {
                state.currentCenter = [50.1016, 53.1949];
                setMapCenter(50.1016, 53.1949, 14);
                placeSingleMarker(state.currentCenter, address);
            }
        });
    }

    /* ==================== Map ==================== */

    function initYandexMapForPvz() {
        if (state.map) return;

        var apiKey = getMapsApiKey();
        if (!apiKey) {
            var mapUnavailable = document.getElementById('mapUnavailableWarning');
            var mapContainer = document.getElementById('yandexMapContainer');
            if (mapContainer) mapContainer.style.display = 'none';
            if (mapUnavailable) mapUnavailable.style.display = 'block';
            return;
        }

        loadYandexMaps().then(function() {
            initYandexMap();
        }).catch(function(err) {
            console.error('[YDW] Failed to load Yandex Maps:', err);
            var mapUnavailable = document.getElementById('mapUnavailableWarning');
            var mapContainer = document.getElementById('yandexMapContainer');
            if (mapContainer) mapContainer.style.display = 'none';
            if (mapUnavailable) mapUnavailable.style.display = 'block';
        });
    }

    function initYandexMap() {
        if (!state.ymaps3) return;
        if (state.map) return;

        try {
            var YMap = state.ymaps3.YMap;
            var YMapDefaultSchemeLayer = state.ymaps3.YMapDefaultSchemeLayer;
            var YMapDefaultFeaturesLayer = state.ymaps3.YMapDefaultFeaturesLayer;
            var YMapCollection = state.ymaps3.YMapCollection;
            var YMapScaleControl = state.ymaps3.YMapScaleControl;

            if (!YMap) {
                console.error('[YDW] YMap constructor not found');
                return;
            }

            var mapElement = document.getElementById('yandexMap');
            if (!mapElement) {
                console.error('[YDW] mapContainer not found');
                return;
            }

            var mapOptions = {
                location: {
                    center: MAP_CENTER,
                    zoom: MAP_DEFAULT_ZOOM
                },
                events: ['click', 'change']
            };

            var map = new YMap(mapElement, mapOptions);
            map.addChild(new YMapDefaultSchemeLayer());
            if (YMapDefaultFeaturesLayer) {
                map.addChild(new YMapDefaultFeaturesLayer());
            }

            var collection = null;
            if (YMapCollection && typeof YMapCollection === 'function') {
                try {
                    collection = new YMapCollection(mapElement, { components: 'points' });
                    map.addChild(collection);
                } catch(e) {
                    console.warn('[YDW] Failed to create collection:', e);
                }
            }

            if (YMapScaleControl) {
                try {
                    var scaleControl = new YMapScaleControl();
                    map.addChild(scaleControl);
                } catch(e) {
                    console.warn('[YDW] Failed to add scale control:', e);
                }
            }

            state.map = map;
            state.markerCollection = collection;

            // Global click handler — stored to prevent leaks
            (function(mapEl, container) {
                state.mapClickHandler = function(globalEvent) {
                    if (!state.map) return;
                    if (!container.contains(globalEvent.target)) return;

                    if (globalEvent.target.closest('button') ||
                        globalEvent.target.tagName === 'BUTTON' ||
                        globalEvent.target.closest('.autocomplete-item')) {
                        return;
                    }

                    // Read current map center/zoom (ymaps3 stores them as getter properties)
                    try {
                        if (state.map.center && Array.isArray(state.map.center)) {
                            state.currentCenter = state.map.center;
                        }
                        if (state.map.zoom !== undefined) {
                            state.currentZoom = state.map.zoom;
                        }
                    } catch(e) {}

                    var rect = mapEl.getBoundingClientRect();
                    var x = globalEvent.clientX - rect.left;
                    var y = globalEvent.clientY - rect.top;

                    if (x < 0 || x > rect.width || y < 0 || y > rect.height) return;

                    var centerX = rect.width / 2;
                    var centerY = rect.height / 2;
                    var pixelDeltaX = x - centerX;
                    var pixelDeltaY = y - centerY;

                    var metersPerPixel = 156543.03392804095 *
                        Math.cos(state.currentCenter[1] * Math.PI / 180) /
                        Math.pow(2, state.currentZoom);

                    var lon = state.currentCenter[0] + pixelDeltaX * metersPerPixel / 111320;
                    var lat = state.currentCenter[1] - pixelDeltaY * metersPerPixel / 111320;

                    // Don't re-center the map on single click — only geocode
                    reverseGeocodeToAddress(lon, lat);
                };

                document.addEventListener('click', state.mapClickHandler);
            })(mapElement, document.getElementById('yandexMapContainer'));

            // Add zoom controls
            setTimeout(function() {
                addHtmlZoomControls(mapElement);
            }, 500);

            loadPvzPoints();
        } catch (e) {
            console.error('[YDW] Yandex Map init error:', e);
        }
    }

    function addHtmlZoomControls(container) {
        var zoomContainer = document.createElement('div');
        zoomContainer.style.cssText = 'position:absolute;top:10px;right:10px;display:flex;flex-direction:column;gap:5px;z-index:100;';

        var btnPlus = document.createElement('button');
        btnPlus.innerHTML = '+';
        btnPlus.style.cssText = 'width:36px;height:36px;font-size:20px;font-weight:bold;border:2px solid #ccc;border-radius:6px;background:#fff;cursor:pointer;box-shadow:0 2px 4px rgba(0,0,0,0.2);';
        btnPlus.addEventListener('click', function() {
            if (state.currentZoom < MAP_MAX_ZOOM) {
                setMapCenterWithZoom(state.currentZoom + 1);
            }
        });

        var btnMinus = document.createElement('button');
        btnMinus.innerHTML = '\u2212';
        btnMinus.style.cssText = 'width:36px;height:36px;font-size:20px;font-weight:bold;border:2px solid #ccc;border-radius:6px;background:#fff;cursor:pointer;box-shadow:0 2px 4px rgba(0,0,0,0.2);';
        btnMinus.addEventListener('click', function() {
            if (state.currentZoom > MAP_MIN_ZOOM) {
                setMapCenterWithZoom(state.currentZoom - 1);
            }
        });

        zoomContainer.appendChild(btnPlus);
        zoomContainer.appendChild(btnMinus);
        container.appendChild(zoomContainer);
    }

    function setMapCenterWithZoom(newZoom) {
        try {
            // Sync state from ymaps3 before zooming — the center may have
            // changed via drag since state.currentCenter was last set.
            if (state.map.center && Array.isArray(state.map.center)) {
                state.currentCenter = state.map.center;
            }
            if (state.map.zoom !== undefined) {
                state.currentZoom = state.map.zoom;
            }

            newZoom = Math.max(MAP_MIN_ZOOM, Math.min(MAP_MAX_ZOOM, newZoom));
            state.currentZoom = newZoom;
            state.map.setLocation({
                center: state.currentCenter,
                zoom: newZoom
            });
        } catch(e) {
            console.error('[YDW] Failed to set zoom:', e);
        }
    }

    function setMapCenter(lat, lon, zoom) {
        state.currentCenter = [lat, lon];
        state.currentZoom = zoom;
        try {
            state.map.setLocation({
                center: [lat, lon],
                zoom: zoom
            });
        } catch(e) {
            console.error('[YDW] Failed to set map center:', e);
        }
    }

    function loadPvzPoints() {
        if (!state.map) return;

        clearMarkers();

        fetch('/checkout/pvz-locations/?type=' + state.selectedType)
            .then(function(response) { return response.json(); })
            .then(function(data) {
                renderPvzPoints(data.points || []);
            })
            .catch(function(err) {
                console.error('[YDW] Failed to load PVZ points:', err);
                renderPvzPoints([]);
            });
    }

    function renderPvzPoints(points) {
        if (!state.map || !state.ymaps3) return;

        clearMarkers();

        var YMapMarker = state.ymaps3.YMapMarker;
        if (!YMapMarker) return;

        points.forEach(function(point) {
            var coordinates = point.coordinates || point.coords || MAP_CENTER;
            var icon = createPvzIcon(point);

            try {
                var marker = new YMapMarker({
                    coordinates: coordinates,
                    icon: icon,
                    onClick: function() {
                        if (state.map) {
                            setMapCenter(coordinates[0], coordinates[1], 16);
                        }

                        state.selectedAddress = point.address || point.name;
                        document.getElementById('yandexAddressInput').value = state.selectedAddress;
                        state.selectedType = point.type || state.selectedType;

                        // Сохраняем station_id и station_name в скрытые поля
                        if (point.id) {
                            var stationIdField = document.getElementById('id_yandex_station_id');
                            var stationNameField = document.getElementById('id_yandex_station_name');
                            if (stationIdField) stationIdField.value = point.id;
                            if (stationNameField) stationNameField.value = point.name || '';
                        }

                        calculateDelivery();
                    }
                });

                state.map.addChild(marker);
                state.markers.push(marker);
            } catch(e) {
                console.error('[YDW] Failed to add PVZ marker:', e);
            }
        });
    }

    function createPvzIcon(point) {
        if (state.selectedType === 'postomat') return ICON_POSTOMAT;
        return ICON_PVZ;
    }

    /* ==================== Delivery ==================== */

    function calculateDelivery() {
        var costEl = document.getElementById('widgetCost');
        var etaEl = document.getElementById('widgetEta');
        var confirmBtn = document.getElementById('confirmDeliveryBtn');

        if (!costEl || !etaEl) return;

        costEl.textContent = 'Расчёт...';
        etaEl.textContent = '';
        if (confirmBtn) confirmBtn.disabled = true;

        var addressValue = state.selectedAddress ||
            document.getElementById('yandexAddressInput')?.value || '';
        if (!addressValue) return;

        var address = CoffeeShop.parseAddress(addressValue);
        address.delivery_type = state.selectedType;

        // Для ПВЗ и Постмат передаём station_id
        if (state.selectedType === 'pvz' || state.selectedType === 'postomat') {
            var selectedMarker = state.markers[state.markers.length - 1];
            // Получаем station_id из выбранной точки
            var stationInput = document.getElementById('id_yandex_station_id');
            if (stationInput && stationInput.value) {
                address.station_id = stationInput.value;
            }
        }

        apiFetch('/checkout/calculate-delivery/', address)
        .then(function (response) { return response.json(); })
        .then(function (data) {
            if (data.success && data.price) {
                state.selectedPrice = data.price;
                state.selectedEta = data.eta || '30-45 мин';
                costEl.textContent = CoffeeShop.formatPrice(data.price) + ' \u20BD';
                etaEl.textContent = data.eta || '30-45 мин';
                updateConfirmButton();
            } else {
                state.selectedPrice = 299;
                state.selectedEta = '30-45 мин';
                costEl.textContent = '299 \u20BD';
                etaEl.textContent = '30-45 мин';
                updateConfirmButton();
            }
        })
        .catch(function () {
            state.selectedPrice = 299;
            state.selectedEta = '30-45 мин';
            costEl.textContent = '299 \u20BD';
            etaEl.textContent = '30-45 мин';
            updateConfirmButton();
        });
    }

    function confirmDelivery() {
        if (!state.selectedType || !state.selectedAddress || state.selectedPrice === null) {
            return;
        }

        var addressField = document.getElementById('id_delivery_address');
        var deliveryTypeField = document.getElementById('id_yandex_delivery_type');
        var stationIdField = document.getElementById('id_yandex_station_id');
        var stationNameField = document.getElementById('id_yandex_station_name');
        var selectedDeliveryCost = document.getElementById('selectedDeliveryCost');
        var orderDeliveryCostSpan = document.getElementById('orderDeliveryCost');
        var selectedDeliveryEta = document.getElementById('selectedDeliveryEta');
        var deliveryInfo = document.getElementById('deliveryInfo');
        var addressBlock = document.getElementById('addressBlock');

        // Store values before hiding address block
        var selectedAddress = state.selectedAddress;
        var selectedPrice = state.selectedPrice;
        var selectedEta = state.selectedEta;
        var selectedType = state.selectedType;

        // Hide address block first
        if (addressBlock) {
            addressBlock.style.display = 'none';
        }

        // Update hidden address field
        if (addressField) {
            addressField.value = selectedAddress;
        }

        // Update delivery type hidden field
        if (deliveryTypeField) {
            deliveryTypeField.value = selectedType;
        }

        // Update delivery cost display in deliveryInfo block
        if (selectedDeliveryCost) {
            selectedDeliveryCost.textContent = CoffeeShop.formatPrice(selectedPrice) + ' ₽';
        }

        // Update order summary delivery cost
        if (orderDeliveryCostSpan) {
            orderDeliveryCostSpan.textContent = CoffeeShop.formatPrice(selectedPrice) + ' ₽';
        }

        // Сохраняем delivery_cost в скрытое поле формы
        var deliveryCostField = document.getElementById('id_yandex_delivery_cost');
        if (deliveryCostField) {
            deliveryCostField.value = selectedPrice;
        }

        // Обновляем ETA
        if (selectedDeliveryEta) {
            selectedDeliveryEta.textContent = selectedEta || '';
        }

        // Показываем блок deliveryInfo
        if (deliveryInfo) {
            deliveryInfo.style.display = 'block';
        }

        // Пересчитываем итоговую сумму заказа
        if (typeof Checkout !== 'undefined' && typeof Checkout.updateOrderTotal === 'function') {
            Checkout.updateOrderTotal(selectedPrice);
        }

        if (window.CoffeeShop && CoffeeShop.showToast) {
            CoffeeShop.showToast('Доставка успешно настроена', 'success');
        }

        // Close modal first
        closeModal();

        // Update delivery info after modal is closed
        setTimeout(function() {
            if (typeof Checkout !== 'undefined') {
                if (typeof Checkout.updateDeliverySummary === 'function') {
                    Checkout.updateDeliverySummary(selectedType);
                }
            }
        }, 300);
    }

    /* ==================== Reset ==================== */

    function resetWidget() {
        state.selectedType = null;
        state.selectedAddress = null;
        state.selectedPrice = null;
        state.selectedEta = null;

        // Hide delivery summary when resetting
        var deliverySummary = document.getElementById('deliverySummary');
        if (deliverySummary) {
            deliverySummary.style.display = 'none';
        }

        // Remove global click handler
        if (state.mapClickHandler) {
            document.removeEventListener('click', state.mapClickHandler);
            state.mapClickHandler = null;
        }

        // Clear map
        clearMarkers();
        state.map = null;
        state.markerCollection = null;
        state.ymaps3 = null;
        state.currentCenter = [50.1016, 53.1949];
        state.currentZoom = 12;

        // Reset radio buttons
        var radios = document.querySelectorAll('input[name="yandex_delivery_type"]');
        radios.forEach(function (r) { r.checked = false; });

        // Reset address input
        var addressInput = document.getElementById('yandexAddressInput');
        if (addressInput) {
            addressInput.value = '';
            if (addressInput._autocompleteHandler) {
                addressInput.removeEventListener('input', addressInput._autocompleteHandler);
                addressInput._autocompleteHandler = null;
            }
        }

        // Reset station fields
        var stationIdField = document.getElementById('id_yandex_station_id');
        var stationNameField = document.getElementById('id_yandex_station_name');
        if (stationIdField) stationIdField.value = '';
        if (stationNameField) stationNameField.value = '';

        // Hide step 3
        var step3 = document.getElementById('deliveryStep3');
        if (step3) step3.style.display = 'none';

        // Hide map and address wrap
        var mapContainer = document.getElementById('yandexMapContainer');
        if (mapContainer) mapContainer.style.display = 'none';
        var addressWrap = document.getElementById('yandexAddressInputWrap');
        if (addressWrap) addressWrap.style.display = 'none';
        var mapUnavailable = document.getElementById('mapUnavailableWarning');
        if (mapUnavailable) mapUnavailable.style.display = 'none';

        // Reset cost and ETA
        var costEl = document.getElementById('widgetCost');
        var etaEl = document.getElementById('widgetEta');
        if (costEl) costEl.textContent = 'Расчёт...';
        if (etaEl) etaEl.textContent = '';

        // Disable confirm button
        var confirmBtn = document.getElementById('confirmDeliveryBtn');
        if (confirmBtn) confirmBtn.disabled = true;

        // Hide autocomplete list
        var list = document.getElementById('yandexAutocompleteList');
        if (list) {
            list.style.display = 'none';
            list.innerHTML = '';
        }

        // Clear autocomplete timeout
        if (state.autocompleteTimeout) {
            clearTimeout(state.autocompleteTimeout);
            state.autocompleteTimeout = null;
        }
    }

    /* ==================== Export ==================== */

    return {
        init: init,
        openModal: openModal,
        getSelectedType: function() { return state.selectedType; }
    };

})();

document.addEventListener('DOMContentLoaded', YandexDeliveryWidget.init);
