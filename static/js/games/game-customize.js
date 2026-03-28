/* ============================================================
   GeoFreak — Game Customization Module
   Manages dataset/filter selection for GeoGames and Outline.
   Exposes window.GeoCustomize.
   ============================================================ */
var GeoCustomize = (function () {
    'use strict';

    /* ── State ─────────────────────────────────────────────── */
    var state = {
        dataset:    'countries',   // 'countries' | 'regions'
        subDataset: 'us-states',   // active when dataset === 'regions'
        continent:  'all',
        entityType: 'all',
    };

    var REGION_DATASETS = [
        'us-states', 'spain-provinces', 'russia-regions',
        'france-regions', 'italy-regions', 'germany-states',
    ];

    /* ── Accessors ─────────────────────────────────────────── */

    function getState() {
        return { dataset: state.dataset, subDataset: state.subDataset,
                 continent: state.continent, entityType: state.entityType };
    }

    /** Returns the effective dataset string for API ?dataset= param. */
    function getApiDataset() {
        return state.dataset === 'countries' ? 'countries' : state.subDataset;
    }

    /** Build the extra query string fragment for quiz API calls. */
    function buildApiParams() {
        var ds = getApiDataset();
        var p = '&dataset=' + encodeURIComponent(ds);
        if (ds === 'countries') {
            if (state.continent && state.continent !== 'all') {
                p += '&continent=' + encodeURIComponent(state.continent);
            }
            if (state.entityType && state.entityType !== 'all') {
                p += '&entity_type=' + encodeURIComponent(state.entityType);
            }
        }
        return p;
    }

    function isSubnational() {
        return state.dataset === 'regions';
    }

    /* ── Modal control ─────────────────────────────────────── */

    function openModal() {
        var modal = document.getElementById('customize-modal');
        if (!modal) return;
        _syncModalToState();
        modal.style.display = 'flex';
    }

    function closeModal() {
        var modal = document.getElementById('customize-modal');
        if (modal) modal.style.display = 'none';
    }

    function applyAndClose() {
        _readModalToState();
        closeModal();
    }

    /* ── Sync helpers ──────────────────────────────────────── */

    function _syncModalToState() {
        var radC = document.getElementById('cust-radio-countries');
        var radR = document.getElementById('cust-radio-regions');
        if (!radC) return;
        var isCountries = state.dataset === 'countries';
        radC.checked = isCountries;
        radR.checked = !isCountries;
        _toggleSubPanels(isCountries);

        var selContinent = document.getElementById('cust-continent');
        if (selContinent) selContinent.value = state.continent;

        var selEntityType = document.getElementById('cust-entity-type');
        if (selEntityType) selEntityType.value = state.entityType;

        var selSub = document.getElementById('cust-sub-dataset');
        if (selSub) selSub.value = state.subDataset;
    }

    function _readModalToState() {
        var radC = document.getElementById('cust-radio-countries');
        if (!radC) return;
        var isCountries = radC.checked;
        state.dataset = isCountries ? 'countries' : 'regions';

        var selContinent = document.getElementById('cust-continent');
        if (selContinent) state.continent = selContinent.value || 'all';

        var selEntityType = document.getElementById('cust-entity-type');
        if (selEntityType) state.entityType = selEntityType.value || 'all';

        var selSub = document.getElementById('cust-sub-dataset');
        if (selSub) state.subDataset = selSub.value || 'us-states';
    }

    function _toggleSubPanels(isCountries) {
        var panelC = document.getElementById('cust-countries-options');
        var panelR = document.getElementById('cust-regions-options');
        if (panelC) panelC.style.display = isCountries ? '' : 'none';
        if (panelR) panelR.style.display = isCountries ? 'none' : '';
    }

    /* ── Init ──────────────────────────────────────────────── */

    function init() {
        var modal = document.getElementById('customize-modal');
        if (!modal) return;

        // Backdrop click to close
        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModal();
        });

        // Radio buttons
        var radC = document.getElementById('cust-radio-countries');
        var radR = document.getElementById('cust-radio-regions');
        if (radC) radC.addEventListener('change', function () { _toggleSubPanels(true); });
        if (radR) radR.addEventListener('change', function () { _toggleSubPanels(false); });
    }

    /* ── Public API ────────────────────────────────────────── */
    return {
        getState:      getState,
        getApiDataset: getApiDataset,
        buildApiParams: buildApiParams,
        isSubnational: isSubnational,
        openModal:     openModal,
        closeModal:    closeModal,
        applyAndClose: applyAndClose,
        init:          init,
        REGION_DATASETS: REGION_DATASETS,
    };
}());

document.addEventListener('DOMContentLoaded', function () { GeoCustomize.init(); });
