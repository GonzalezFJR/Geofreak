/* ============================================================
   GeoFreak — Map Game Engine
   Multi-dataset map challenge:
     datasets: countries | cities | us-states | spain-provinces | russia-regions
     modes: type (name it) | click (locate it)
   ============================================================ */

var MapGame = (function () {
    var map, geojsonLayer;
    var entityLayers   = {};  // id → Leaflet polygon layer (polygon datasets)
    var cityMarkers    = {};  // id → Leaflet circle marker (cities dataset)
    var entitiesData   = {};  // id → entity data object
    var targetIds      = [];
    var targetSet      = null;
    var correctSet     = null;
    var failedSet      = null;
    var selectedId     = null;
    var activeTooltipLayer = null;
    var mode, dataset;
    var isCityDataset  = false;
    var inputEl        = null;
    var answerIndex    = {};  // normalizedName → id

    /* Cities locate mode state */
    var cityLocateQueue    = [];
    var cityLocateTarget   = null;
    var cityLocateTempMarkers = [];
    var CITY_LOCATE_KM     = 400;  // acceptance threshold in km
    var _cityTooltipTimer  = null;

    /* ── Map config per dataset ─────────────────────────────── */
    var DATASET_CONFIG = {
        'countries':        { center: [20,  0],  zoom: 2, minZoom: 2, maxBounds: null },
        'cities':           { center: [20,  0],  zoom: 2, minZoom: 2, maxBounds: null },
        'us-states':        { center: [39, -98], zoom: 4, minZoom: 3,
                              maxBounds: [[-26, -138], [85, -54]] },
        'spain-provinces':  { center: [40,  -4], zoom: 5, minZoom: 4,
                              maxBounds: [[ 8,  -17], [71,  12]] },
        'russia-regions':   { center: [62,  90], zoom: 3, minZoom: 3,
                              maxBounds: [[-19,    8], [85, 200]] },
        'france-regions':   { center: [46,   2], zoom: 5, minZoom: 4,
                              maxBounds: null },
        'italy-provinces':    { center: [42,  12], zoom: 5, minZoom: 4,
                              maxBounds: [[35,   6], [48,  19]] },
        'germany-states':   { center: [51,  10], zoom: 5, minZoom: 4,
                              maxBounds: [[46,   5], [56,  16]] },
        'mexico-states':    { center: [23, -102], zoom: 5, minZoom: 4,
                              maxBounds: [[14, -118], [33, -86]] },
        'argentina-provinces': { center: [-38, -64], zoom: 4, minZoom: 3,
                              maxBounds: [[-56, -76], [-21, -52]] },
        'brazil-states':    { center: [-14, -52], zoom: 4, minZoom: 3,
                              maxBounds: [[-34, -75], [6, -34]] },
    };

    /* ── Map config per continent (countries dataset filtered) ── */
    var CONTINENT_CONFIG = {
        'europe':   { center: [54,  15], zoom: 4, minZoom: 3, maxBounds: [[-17, -28], [85,  52]] },
        'asia':     { center: [35,  90], zoom: 3, minZoom: 2, maxBounds: [[-85,  25], [85, 180]] },
        'africa':   { center: [ 5,  20], zoom: 3, minZoom: 2, maxBounds: [[-85, -22], [85,  58]] },
        'americas': { center: [10, -78], zoom: 3, minZoom: 2, maxBounds: [[-85, -130], [85, -25]] },
        'oceania':  { center: [-15, 178], zoom: 3, minZoom: 2, maxBounds: [[-55, 100], [30, 240]] },
    };

    var activeContinent = null; // set during loadData

    /* Returns the right map cfg for dataset + active continent filter */
    function getMapConfig(ds, continent) {
        if (continent && continent !== 'all' && CONTINENT_CONFIG[continent]) {
            return CONTINENT_CONFIG[continent];
        }
        return DATASET_CONFIG[ds] || DATASET_CONFIG['countries'];
    }

    /* ── Oceania antimeridian helpers ──────────────────────── */
    /* Oceania spans the antimeridian (~108°E to ~-130°W).
       To display it contiguously, shift all negative longitudes
       by +360 so they appear east of the dateline. */
    function wrapLon(lon) {
        if (activeContinent === 'oceania' && lon < 0) return lon + 360;
        return lon;
    }

    function shiftGeoJSONCoords(geojson) {
        if (activeContinent !== 'oceania') return geojson;
        var shifted = JSON.parse(JSON.stringify(geojson));
        function walk(coords) {
            if (typeof coords[0] === 'number') {
                // [lon, lat] pair
                if (coords[0] < 0) coords[0] += 360;
                return;
            }
            for (var i = 0; i < coords.length; i++) walk(coords[i]);
        }
        if (shifted.type === 'FeatureCollection') {
            shifted.features.forEach(function (f) { walk(f.geometry.coordinates); });
        } else if (shifted.type === 'Feature') {
            walk(shifted.geometry.coordinates);
        }
        return shifted;
    }

    /* ── Prompt/placeholder keys per dataset ────────────────── */
    var PH_TYPE_KEY  = {
        'countries':       'mg.ph_type_country',
        'cities':          'mg.ph_type_city',
        'us-states':       'mg.ph_type_state',
        'spain-provinces': 'mg.ph_type_province',
        'russia-regions':  'mg.ph_type_region',
        'france-regions':  'mg.ph_type_region',
        'italy-provinces':   'mg.ph_type_province',
        'germany-states':  'mg.ph_type_state',
        'mexico-states':   'mg.ph_type_state',
        'argentina-provinces': 'mg.ph_type_province',
        'brazil-states':   'mg.ph_type_state',
    };
    var PH_CLICK_KEY = {
        'countries':       'mg.ph_country',
        'cities':          'mg.ph_city',
        'us-states':       'mg.ph_state',
        'spain-provinces': 'mg.ph_province',
        'russia-regions':  'mg.ph_region',
        'france-regions':  'mg.ph_region',
        'italy-provinces':   'mg.ph_province',
        'germany-states':  'mg.ph_state',
        'mexico-states':   'mg.ph_state',
        'argentina-provinces': 'mg.ph_province',
        'brazil-states':   'mg.ph_state',
    };
    var WHAT_KEY = {
        'countries':       'mg.what_country',
        'cities':          'mg.what_city',
        'us-states':       'mg.what_state',
        'spain-provinces': 'mg.what_province',
        'russia-regions':  'mg.what_region',
        'france-regions':  'mg.what_region',
        'italy-provinces':   'mg.what_province',
        'germany-states':  'mg.what_state',
        'mexico-states':   'mg.what_state',
        'argentina-provinces': 'mg.what_province',
        'brazil-states':   'mg.what_state',
    };

    /* ── Init ───────────────────────────────────────────────── */
    function init() {
        GeoGame.init({ onStart: loadData, delayTimer: true });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && inputEl) submitAnswer();
        });
    }

    /* ── Spinner ────────────────────────────────────────────── */
    function showSpinner() {
        var mapEl = document.getElementById('game-map');
        if (!mapEl) return;
        var sp = document.createElement('div');
        sp.id = 'map-spinner';
        sp.className = 'map-spinner-overlay';
        sp.innerHTML = '<div class="map-spinner"></div>';
        mapEl.appendChild(sp);
    }
    function hideSpinner() {
        var sp = document.getElementById('map-spinner');
        if (sp) sp.remove();
    }

    /* ── Read settings from hidden inputs ───────────────────── */
    function readSettings() {
        dataset = (document.getElementById('map-dataset-value') || {}).value || 'countries';
        mode    = (document.getElementById('map-mode-value')    || {}).value || 'type';
        isCityDataset = (dataset === 'cities');

        var continent  = (document.getElementById('map-continent-value')       || {}).value || 'all';
        var entityType = (document.getElementById('map-entity-type-value')     || {}).value || 'all';
        var cityFilter = (document.getElementById('map-city-filter-value')     || {}).value || 'capitals';
        var cityContinent = (document.getElementById('map-city-continent-value') || {}).value || 'all';
        var cityCountries = (document.getElementById('map-city-countries-value') || {}).value || '';

        // Build data API URL
        var dataUrl = '/api/map-game/data?dataset=' + encodeURIComponent(dataset);
        if (dataset === 'countries') {
            if (continent  && continent  !== 'all') dataUrl += '&continent='    + encodeURIComponent(continent);
            if (entityType && entityType !== 'all') dataUrl += '&entity_type='  + encodeURIComponent(entityType);
        }
        if (dataset === 'cities') {
            dataUrl += '&city_filter=' + encodeURIComponent(cityFilter);
            if (cityContinent && cityContinent !== 'all') dataUrl += '&continent=' + encodeURIComponent(cityContinent);
            if (cityCountries) dataUrl += '&country_filter=' + encodeURIComponent(cityCountries);
        }

        return { dataUrl: dataUrl, continent: isCityDataset ? cityContinent : continent, entityType: entityType };
    }

    /* ── Data loading ───────────────────────────────────────── */
    function loadData() {
        var s = readSettings();
        activeContinent = s.continent || null;

        // Show UI for the chosen mode
        var promptBar = document.getElementById('game-prompt');
        var inputBar  = document.getElementById('game-input-bar');
        var cityPrompt = document.getElementById('city-locate-prompt');

        if (mode === 'click' && isCityDataset) {
            if (promptBar)  promptBar.style.display  = 'none';
            if (inputBar)   inputBar.style.display   = 'none';
            if (cityPrompt) cityPrompt.style.display = 'flex';
            inputEl = null;
        } else if (mode === 'click') {
            if (promptBar)  promptBar.style.display  = 'none'; // shown on click
            if (inputBar)   inputBar.style.display   = 'none';
            if (cityPrompt) cityPrompt.style.display = 'none';
            inputEl = document.getElementById('answer-input-locate');
        } else {
            if (promptBar)  promptBar.style.display  = 'none';
            if (inputBar)   inputBar.style.display   = '';
            if (cityPrompt) cityPrompt.style.display = 'none';
            inputEl = document.getElementById('answer-input-name');
        }

        // Set placeholder
        if (inputEl) {
            var phKey = mode === 'type' ? PH_TYPE_KEY[dataset] : PH_CLICK_KEY[dataset];
            inputEl.placeholder = T[phKey] || '';
        }

        GeoGame.beginPlay();
        showSpinner();

        var geojsonUrl = '/api/map-game/geojson?dataset=' + encodeURIComponent(dataset);
        var promises   = [fetch(s.dataUrl).then(function (r) { return r.json(); })];
        if (!isCityDataset) {
            promises.push(fetch(geojsonUrl).then(function (r) { return r.json(); }));
        }

        Promise.all(promises).then(function (res) {
            var entities = res[0];
            var geojson  = isCityDataset ? null : res[1];

            setupEntities(entities);
            GeoGame.setTotal(targetSet.size);

            var N = targetSet.size;
            if (GeoGame.settings.timeLimit > 0) {
                var mapDefaults = (window.GAME_CONFIG && window.GAME_CONFIG.defaults) ? window.GAME_CONFIG.defaults : {};
                var secsType  = mapDefaults.secs_per_item_type  || 4;
                var secsClick = mapDefaults.secs_per_item_click || 6;
                var factor  = (mode === 'type') ? secsType : secsClick;
                var minutes = Math.floor(N * factor / 60) + 1;
                var secs = minutes * 60;
                GeoGame.settings.timeLimit = secs;
                GeoGame.timeRemaining      = secs;
                GeoGame._updateTimer();
            }

            var cfg = getMapConfig(dataset, s.continent);
            initMap(geojson, cfg, entities);
            hideSpinner();
            GeoGame.startTimer();

            if (mode === 'type') {
                if (inputEl) inputEl.focus();
                updateRevealButton();
            } else if (mode === 'click' && isCityDataset) {
                startCityLocate();
            }
        }).catch(function (err) {
            hideSpinner();
            console.error('MapGame loadData error:', err);
        });
    }

    /* ── Entity setup ───────────────────────────────────────── */
    function setupEntities(entities) {
        entityLayers = {};
        cityMarkers  = {};
        entitiesData = {};
        targetIds    = [];
        targetSet    = new Set();
        correctSet   = new Set();
        failedSet    = new Set();
        answerIndex  = {};
        selectedId   = null;

        entities.forEach(function (e) {
            entitiesData[e.id] = e;
            targetIds.push(e.id);
            targetSet.add(e.id);

            var names = getEntityNames(e);
            names.forEach(function (n) {
                if (!answerIndex[n]) answerIndex[n] = e.id;  // first match wins
            });
        });
    }

    function getEntityNames(entity) {
        if (dataset === 'countries') {
            return GeoUtils.getCountryNames(entity);
        }
        if (dataset === 'cities') {
            var ns = new Set();
            if (entity.name)      ns.add(GeoUtils.normalize(entity.name));
            if (entity.asciiname) ns.add(GeoUtils.normalize(entity.asciiname));
            return ns;
        }
        // sub-nationals
        var ns2 = new Set();
        if (entity.name)    ns2.add(GeoUtils.normalize(entity.name));
        if (entity.name_es) ns2.add(GeoUtils.normalize(entity.name_es));
        if (entity.name_ru) ns2.add(GeoUtils.normalize(entity.name_ru));
        ns2.delete('');
        return ns2;
    }

    function getEntityLabel(entity) {
        var lang = window.LANG || 'es';
        if (dataset === 'countries') return GeoUtils.getLocalName(entity);
        if (entity['name_' + lang]) return entity['name_' + lang];
        if (entity.name_es && lang !== 'en') return entity.name_es;
        return entity.name;
    }

    /* ── Map initialisation ─────────────────────────────────── */
    function initMap(geojson, cfg, entities) {
        var opts = {
            center: cfg.center,
            zoom: cfg.zoom,
            minZoom: cfg.minZoom || 2,
            maxZoom: 10,
            zoomControl: true,
            worldCopyJump: !cfg.maxBounds,
        };
        if (cfg.maxBounds) {
            opts.maxBounds = cfg.maxBounds;
            opts.maxBoundsViscosity = 1.0;
        }
        map = L.map('game-map', opts);
        window._leaflet_map_ref = map;

        L.tileLayer(
            'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
            { attribution: '© CARTO', subdomains: 'abcd' }
        ).addTo(map);

        if (isCityDataset) {
            initCityMarkers(entities);
        } else {
            initPolygonLayer(shiftGeoJSONCoords(geojson));
        }

        map.on('click', function (e) {
            if (mode === 'click' && isCityDataset) {
                onMapClickCityLocate(e);
                return;
            }
            closeActiveTooltip();
            if (mode === 'type' && selectedId) {
                var prev = selectedId;
                selectedId = null;
                if (isCityDataset) refreshCityStyle(prev);
                else refreshStyle(prev);
                updateRevealButton();
            }
        });
    }

    function initPolygonLayer(geojson) {
        geojsonLayer = L.geoJSON(geojson, {
            style: function (f) { return styleFor(f); },
            onEachFeature: function (f, layer) {
                var id = getFeatureId(f);
                if (!id) return;
                entityLayers[id] = layer;

                layer.on('click', function (e) {
                    L.DomEvent.stopPropagation(e);
                    onClickPolygon(id);
                });
                layer.on('mouseover', function () {
                    if (targetSet.has(id) && !correctSet.has(id) && !failedSet.has(id)) {
                        layer.setStyle({ fillOpacity: 0.5 });
                    }
                });
                layer.on('mouseout', function () {
                    geojsonLayer.resetStyle(layer);
                });
            },
        }).addTo(map);
    }

    function initCityMarkers(entities) {
        entities.forEach(function (city) {
            var marker = L.circleMarker([city.lat, wrapLon(city.lon)], cityStyle(city.id));
            marker.on('click', function (e) {
                L.DomEvent.stopPropagation(e);
                if (mode === 'type') onClickCity(city.id);
            });
            marker.addTo(map);
            cityMarkers[city.id] = marker;
        });
    }

    /* ── ID extraction ─────────────────────────────────────── */
    function getFeatureId(feature) {
        var p = feature.properties || {};
        // Sub-national datasets tag _game_id via geodata service
        if (p._game_id) return p._game_id;
        // Countries: ISO_A3
        var iso3 = p.ISO_A3 || p.iso_a3 || p.ISO_A3_EH || '';
        return iso3 || null;
    }

    /* ── Polygon styling ────────────────────────────────────── */
    function styleFor(feature) {
        var id = getFeatureId(feature);
        if (failedSet && failedSet.has(id))  return { fillColor: '#ef5350', fillOpacity: 0.55, color: '#c62828', weight: 1.5 };
        if (correctSet && correctSet.has(id)) return { fillColor: '#4caf50', fillOpacity: 0.6,  color: '#2e7d32', weight: 1.5 };
        if (selectedId === id)                return { fillColor: '#1a73e8', fillOpacity: 0.45, color: '#0d47a1', weight: 2 };
        if (targetSet && targetSet.has(id))   return { fillColor: '#e2e8f0', fillOpacity: 0.5,  color: '#94a3b8', weight: 1 };
        return { fillColor: '#f1f5f9', fillOpacity: 0.25, color: '#cbd5e1', weight: 0.5 };
    }

    function refreshStyle(id) {
        var layer = entityLayers[id];
        if (!layer) return;
        var f = layer.feature || (layer.getLayers && layer.getLayers()[0] && layer.getLayers()[0].feature);
        if (f) layer.setStyle(styleFor(f));
    }

    /* ── City marker styling ────────────────────────────────── */
    function cityStyle(id) {
        if (failedSet && failedSet.has(id))  return { radius: 7, fillColor: '#ef5350', color: '#c62828', weight: 1.5, fillOpacity: 0.85 };
        if (correctSet && correctSet.has(id)) return { radius: 7, fillColor: '#4caf50', color: '#2e7d32', weight: 1.5, fillOpacity: 0.9 };
        if (selectedId === id)                return { radius: 8, fillColor: '#1a73e8', color: '#0d47a1', weight: 2,   fillOpacity: 0.7 };
        if (targetSet && targetSet.has(id))   return { radius: 5, fillColor: '#78909c', color: '#455a64', weight: 1,   fillOpacity: 0.55 };
        return { radius: 4, fillColor: '#cfd8dc', color: '#b0bec5', weight: 0.5, fillOpacity: 0.4 };
    }

    function refreshCityStyle(id) {
        var m = cityMarkers[id];
        if (m) m.setStyle(cityStyle(id));
    }

    /* ── Tooltip helpers ────────────────────────────────────── */
    function closeActiveTooltip() {
        if (activeTooltipLayer) {
            try { activeTooltipLayer.closeTooltip(); activeTooltipLayer.unbindTooltip(); } catch (e) {}
            activeTooltipLayer = null;
        }
    }

    function showPolygonTooltip(id) {
        closeActiveTooltip();
        var e   = entitiesData[id];
        var lyr = entityLayers[id];
        if (!e || !lyr) return;
        var label = getEntityLabel(e);
        lyr.bindTooltip(label, { permanent: true, className: 'reveal-tooltip', direction: 'center' }).openTooltip();
        activeTooltipLayer = lyr;
    }

    /* ── City tooltip (timed) ───────────────────────────────── */
    function showCityTooltip(id) {
        var entity = entitiesData[id];
        var marker = cityMarkers[id];
        if (!entity || !marker) return;
        // Close any open city tooltip
        if (_cityTooltipTimer) { clearTimeout(_cityTooltipTimer); _cityTooltipTimer = null; }
        Object.keys(cityMarkers).forEach(function (mid) {
            try { cityMarkers[mid].closeTooltip(); cityMarkers[mid].unbindTooltip(); } catch (e) {}
        });
        var label = getEntityLabel(entity);
        marker.bindTooltip(label, { permanent: true, className: 'reveal-tooltip', direction: 'top' }).openTooltip();
        _cityTooltipTimer = setTimeout(function () {
            try { marker.closeTooltip(); marker.unbindTooltip(); } catch (e) {}
            _cityTooltipTimer = null;
        }, 2500);
    }

    /* ── Reveal button (type mode) ──────────────────────────── */
    function updateRevealButton() {
        if (mode !== 'type') return;
        var btn = document.getElementById('btn-reveal-bar');
        if (btn) btn.disabled = !selectedId;
    }

    /* ── Click on polygon ───────────────────────────────────── */
    function onClickPolygon(id) {
        if (correctSet.has(id) || failedSet.has(id)) {
            if (activeTooltipLayer === entityLayers[id]) closeActiveTooltip();
            else showPolygonTooltip(id);
            return;
        }
        if (!targetSet.has(id)) return;
        closeActiveTooltip();

        var prevId = selectedId;
        selectedId = id;
        if (prevId && prevId !== id) refreshStyle(prevId);
        refreshStyle(id);

        if (mode === 'click') {
            var prompt  = document.getElementById('game-prompt');
            var ptxt    = document.getElementById('prompt-text');
            var pcountry = document.getElementById('prompt-country');
            if (pcountry) pcountry.textContent = '';
            if (ptxt)     ptxt.textContent = T[WHAT_KEY[dataset]] || '?';
            if (prompt)   prompt.style.display = 'flex';
            if (inputEl)  { inputEl.value = ''; inputEl.focus(); }
        } else {
            updateRevealButton();
        }
    }

    /* ── Click on city marker (type mode) ───────────────────── */
    function onClickCity(id) {
        if (correctSet.has(id) || failedSet.has(id)) {
            showCityTooltip(id);
            return;
        }
        if (!targetSet.has(id)) return;
        var prevId = selectedId;
        selectedId = id;
        if (prevId && prevId !== id) refreshCityStyle(prevId);
        refreshCityStyle(id);
        updateRevealButton();
    }

    /* ── Submit answer ─────────────────────────────────────── */
    function submitAnswer() {
        if (!inputEl) return;
        var answer = GeoUtils.normalize(inputEl.value.trim());
        if (!answer) return;

        if (mode === 'click' && !isCityDataset) {
            submitClickPolygon(answer);
        } else {
            submitType(answer);
        }
    }

    function submitClickPolygon(answer) {
        if (!selectedId) return;
        var entity = entitiesData[selectedId];
        if (!entity) return;
        var acceptable = getEntityNames(entity);
        if (acceptable.has(answer)) {
            markCorrect(selectedId);
            if (inputEl) inputEl.value = '';
            var prompt = document.getElementById('game-prompt');
            if (prompt) prompt.style.display = 'none';
            selectedId = null;
            checkComplete();
        } else {
            flashInput(inputEl, false);
        }
    }

    function submitType(answer) {
        var id = answerIndex[answer];
        if (id && targetSet.has(id) && !correctSet.has(id) && !failedSet.has(id)) {
            markCorrect(id);
            if (selectedId === id) {
                selectedId = null;
                updateRevealButton();
            }
            flashInput(inputEl, true);
            if (inputEl) { inputEl.value = ''; inputEl.focus(); }
            showTypeFeedback(true, entitiesData[id]);
            checkComplete();
        } else {
            flashInput(inputEl, false);
            showTypeFeedback(false);
        }
    }

    /* ── Mark correct / failed ─────────────────────────────── */
    function markCorrect(id) {
        correctSet.add(id);
        GeoGame.addCorrect();
        GeoGame.addAnswered();
        if (isCityDataset) refreshCityStyle(id);
        else refreshStyle(id);
    }

    function markFailed(id) {
        failedSet.add(id);
        GeoGame.addAnswered();
        if (isCityDataset) refreshCityStyle(id);
        else refreshStyle(id);
    }

    function checkComplete() {
        if ((correctSet.size + failedSet.size) >= targetSet.size) {
            setTimeout(function () { GeoGame.endGame(); }, 600);
        }
    }

    /* ── Type feedback ─────────────────────────────────────── */
    function flashInput(el, success) {
        if (!el) return;
        var cls = success ? 'correct-flash' : 'wrong-flash';
        el.classList.add(cls);
        setTimeout(function () { el.classList.remove(cls); }, success ? 600 : 400);
    }

    function showTypeFeedback(ok, entity) {
        var el = document.getElementById('input-feedback');
        if (!el) return;
        if (ok && entity) {
            el.className = 'input-feedback correct';
            el.textContent = '✅ ' + getEntityLabel(entity);
        } else {
            el.className = 'input-feedback wrong';
            el.textContent = T['js.no_match'] || '❌ No match';
        }
        clearTimeout(el._timer);
        el._timer = setTimeout(function () {
            el.className = 'input-feedback';
            el.textContent = '';
        }, 1500);
    }

    /* ── Reveal ────────────────────────────────────────────── */
    function reveal() {
        if (mode === 'click' && isCityDataset) return; // handled via skip
        if (mode === 'click') revealClick();
        else revealType();
    }

    function revealClick() {
        if (!selectedId) return;
        var entity = entitiesData[selectedId];
        if (!entity) return;
        var answer = getEntityLabel(entity);
        if (inputEl) inputEl.value = answer;
        markFailed(selectedId);
        showPolygonTooltip(selectedId);
        var prompt = document.getElementById('game-prompt');
        var id = selectedId;
        setTimeout(function () {
            closeActiveTooltip();
            if (prompt) prompt.style.display = 'none';
            selectedId = null;
            checkComplete();
        }, 1500);
    }

    function revealType() {
        if (!selectedId) return;
        var id = selectedId;
        var entity = entitiesData[id];
        if (!entity) return;
        markFailed(id);
        var label = getEntityLabel(entity);
        var el = document.getElementById('input-feedback');
        if (el) {
            el.className = 'input-feedback wrong';
            el.textContent = (T['js.revealed'] || '👁️ {name}').replace('{name}', label);
            clearTimeout(el._timer);
            el._timer = setTimeout(function () {
                el.className = 'input-feedback';
                el.textContent = '';
            }, 2000);
        }
        if (!isCityDataset) showPolygonTooltip(id);
        selectedId = null;
        updateRevealButton();
        setTimeout(function () { closeActiveTooltip(); }, 1500);
        checkComplete();
    }

    /* ── Cities locate mode ─────────────────────────────────── */
    function startCityLocate() {
        cityLocateQueue = GeoUtils.shuffle(targetIds.slice());
        cityLocateTempMarkers = [];
        advanceCityLocate();
    }

    function advanceCityLocate() {
        // Clean up temp markers from previous round
        cityLocateTempMarkers.forEach(function (m) { map.removeLayer(m); });
        cityLocateTempMarkers = [];

        if (cityLocateQueue.length === 0) {
            checkComplete();
            return;
        }
        cityLocateTarget = entitiesData[cityLocateQueue.shift()];
        if (!cityLocateTarget) { advanceCityLocate(); return; }

        var promptEl = document.getElementById('city-locate-text');
        if (promptEl) {
            promptEl.textContent = getEntityLabel(cityLocateTarget) + ' →  ?';
        }
        var promptBar = document.getElementById('city-locate-prompt');
        if (promptBar) promptBar.style.display = 'flex';
    }

    function onMapClickCityLocate(e) {
        if (!cityLocateTarget) return;
        var city = cityLocateTarget;
        var targetLL   = L.latLng(city.lat, wrapLon(city.lon));
        var clickLL    = e.latlng;
        var distKm     = clickLL.distanceTo(targetLL) / 1000;
        var correct    = distKm <= CITY_LOCATE_KM;

        // Show where user clicked
        var clickDot = L.circleMarker(clickLL, {
            radius: 6, fillColor: correct ? '#4caf50' : '#ef5350',
            color: correct ? '#2e7d32' : '#c62828', weight: 2, fillOpacity: 0.9,
        }).addTo(map);
        cityLocateTempMarkers.push(clickDot);

        // Show actual city location (if wrong, so user can learn)
        if (!correct) {
            var actualDot = L.circleMarker(targetLL, {
                radius: 8, fillColor: '#ff9800', color: '#e65100',
                weight: 2, fillOpacity: 0.9,
            }).addTo(map);
            cityLocateTempMarkers.push(actualDot);
            var line = L.polyline([clickLL, targetLL], { color: '#ff9800', weight: 1.5, dashArray: '4,4' }).addTo(map);
            cityLocateTempMarkers.push(line);
        }

        if (correct) {
            markCorrect(city.id);
        } else {
            markFailed(city.id);
        }

        // Feedback on city prompt
        var promptEl = document.getElementById('city-locate-text');
        if (promptEl) {
            var distStr = Math.round(distKm) + ' km';
            promptEl.textContent = correct
                ? '✅ ' + getEntityLabel(city) + ' (' + distStr + ')'
                : '❌ ' + getEntityLabel(city) + ' — ' + distStr;
        }

        cityLocateTarget = null;
        setTimeout(function () {
            advanceCityLocate();
            checkComplete();
        }, 1600);
    }

    return {
        init: init,
        submitAnswer: submitAnswer,
        reveal: reveal,
        getConfig: function () { return { dataset: dataset, mode: mode }; }
    };
})();
