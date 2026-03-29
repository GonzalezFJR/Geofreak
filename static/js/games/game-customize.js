/* ============================================================
   GeoFreak — Game Customization Module
   Inline expandable panel for GeoGames and Outline quiz.
   Exposes window.GeoCustomize.
   ============================================================ */
var GeoCustomize = (function () {
    'use strict';

    /* ── State ─────────────────────────────────────────────── */
    var state = {
        dataset:       'countries',   // 'countries' | 'cities' | 'regions'
        subDataset:    'us-states',   // active when dataset === 'regions'
        continent:     'all',
        entityType:    'all',
        cityContinent: 'all',
        cityFilter:    '1m',
        cityCountries: [],            // list of iso_a3
    };

    var REGION_DATASETS = [
        'us-states', 'spain-provinces', 'russia-regions',
        'france-regions', 'italy-regions', 'germany-states',
    ];

    // Module-scope reference so continent pills handler can reset it
    var _cityCountrySelect = null;

    /* ── Accessors ─────────────────────────────────────────── */

    function getState() {
        return {
            dataset:       state.dataset,
            subDataset:    state.subDataset,
            continent:     state.continent,
            entityType:    state.entityType,
            cityContinent: state.cityContinent,
            cityFilter:    state.cityFilter,
            cityCountries: state.cityCountries.slice(),
        };
    }

    function getApiDataset() {
        if (state.dataset === 'cities') return 'cities';
        return state.dataset === 'countries' ? 'countries' : state.subDataset;
    }

    function buildApiParams() {
        var ds = getApiDataset();
        var p = '&dataset=' + encodeURIComponent(ds);
        if (ds === 'countries') {
            if (state.continent && state.continent !== 'all')
                p += '&continent=' + encodeURIComponent(state.continent);
            if (state.entityType && state.entityType !== 'all')
                p += '&entity_type=' + encodeURIComponent(state.entityType);
        } else if (ds === 'cities') {
            if (state.cityContinent && state.cityContinent !== 'all')
                p += '&continent=' + encodeURIComponent(state.cityContinent);
            if (state.cityFilter)
                p += '&city_filter=' + encodeURIComponent(state.cityFilter);
            if (state.cityCountries.length)
                p += '&country_filter=' + encodeURIComponent(state.cityCountries.join(','));
        }
        return p;
    }

    function isSubnational() { return state.dataset === 'regions'; }

    function getCityFilter()    { return state.cityFilter; }
    function getCityCountries() { return state.cityCountries.slice(); }

    /* ── Panel toggle ──────────────────────────────────────── */

    function togglePanel() {
        var panel = document.getElementById('gcust-panel');
        if (!panel) return;
        var open = panel.style.display !== 'none' && panel.style.display !== '';
        panel.style.display = open ? 'none' : '';
        var gearBtn = document.getElementById('gcust-gear-btn');
        if (gearBtn) gearBtn.classList.toggle('active', !open);
    }

    /* ── Deprecated aliases (kept for backward compat) ─────── */
    function openModal()  { togglePanel(); }
    function closeModal() { togglePanel(); }

    /* ── Sync UI to state ──────────────────────────────────── */

    function _syncTypeTabs() {
        var tabs = document.querySelectorAll('#gcust-type-tabs .gcust-tab');
        tabs.forEach(function (t) {
            t.classList.toggle('active', t.getAttribute('data-type') === state.dataset);
        });
        var optsC   = document.getElementById('gcust-countries-opts');
        var optsR   = document.getElementById('gcust-regions-opts');
        var optsCit = document.getElementById('gcust-cities-opts');
        if (optsC)   optsC.style.display   = state.dataset === 'countries' ? '' : 'none';
        if (optsR)   optsR.style.display   = state.dataset === 'regions'   ? '' : 'none';
        if (optsCit) optsCit.style.display = state.dataset === 'cities'    ? '' : 'none';
    }

    function _syncContinentPills() {
        document.querySelectorAll('#gcust-continent-pills .mcfg-pill').forEach(function (p) {
            p.classList.toggle('active', p.getAttribute('data-value') === state.continent);
        });
    }

    function _syncRegionCards() {
        document.querySelectorAll('#gcust-region-cards .mcfg-region-card').forEach(function (c) {
            c.classList.toggle('active', c.getAttribute('data-value') === state.subDataset);
        });
    }

    function _syncCitiesContinentPills() {
        document.querySelectorAll('#gcust-cities-continent-pills .mcfg-pill').forEach(function (p) {
            p.classList.toggle('active', p.getAttribute('data-value') === state.cityContinent);
        });
    }

    function _syncCityPopPills() {
        document.querySelectorAll('#gcust-city-pop-pills .mcfg-pill').forEach(function (p) {
            p.classList.toggle('active', p.getAttribute('data-value') === state.cityFilter);
        });
    }

    /* ── Init ──────────────────────────────────────────────── */

    function init() {
        // Type tabs
        document.querySelectorAll('#gcust-type-tabs .gcust-tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                state.dataset = tab.getAttribute('data-type');
                _syncTypeTabs();
            });
        });

        // Continent pills (countries)
        document.querySelectorAll('#gcust-continent-pills .mcfg-pill').forEach(function (pill) {
            pill.addEventListener('click', function () {
                state.continent = pill.getAttribute('data-value');
                _syncContinentPills();
            });
        });

        // Region cards
        document.querySelectorAll('#gcust-region-cards .mcfg-region-card').forEach(function (card) {
            card.addEventListener('click', function () {
                state.subDataset = card.getAttribute('data-value');
                _syncRegionCards();
            });
        });

        // Cities continent pills
        document.querySelectorAll('#gcust-cities-continent-pills .mcfg-pill').forEach(function (pill) {
            pill.addEventListener('click', function () {
                state.cityContinent = pill.getAttribute('data-value');
                _syncCitiesContinentPills();
                // clear country filter when continent changes
                state.cityCountries = [];
                if (_cityCountrySelect) _cityCountrySelect.reset();
            });
        });

        // City population pills
        document.querySelectorAll('#gcust-city-pop-pills .mcfg-pill').forEach(function (pill) {
            pill.addEventListener('click', function () {
                state.cityFilter = pill.getAttribute('data-value');
                _syncCityPopPills();
            });
        });

        // Country multi-select for cities
        if (typeof GeoUtils !== 'undefined' && GeoUtils.buildCountrySelect) {
            var csContainer = document.getElementById('gcust-city-country-select');
            if (csContainer) {
                var pageLang = document.documentElement.lang || 'es';
                _cityCountrySelect = GeoUtils.buildCountrySelect({
                    container: csContainer,
                    placeholder: pageLang === 'es' ? 'Buscar país...' : 'Search country...',
                    lang: pageLang,
                    onChange: function (isoList) {
                        state.cityCountries = isoList;
                        // clear continent filter when countries are selected
                        if (isoList.length > 0) {
                            state.cityContinent = 'all';
                            _syncCitiesContinentPills();
                        }
                    }
                });
            }
        }
    }

    /* ── Public API ────────────────────────────────────────── */
    return {
        getState:        getState,
        getApiDataset:   getApiDataset,
        buildApiParams:  buildApiParams,
        isSubnational:   isSubnational,
        getCityFilter:   getCityFilter,
        getCityCountries: getCityCountries,
        togglePanel:     togglePanel,
        openModal:       openModal,
        closeModal:      closeModal,
        init:            init,
        REGION_DATASETS: REGION_DATASETS,
    };
}());

document.addEventListener('DOMContentLoaded', function () { GeoCustomize.init(); });
