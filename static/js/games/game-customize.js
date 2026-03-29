/* ============================================================
   GeoFreak — Game Customization Module
   Inline expandable panel for GeoGames and Outline quiz.
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

    function getApiDataset() {
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
        }
        return p;
    }

    function isSubnational() { return state.dataset === 'regions'; }

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
        var optsC = document.getElementById('gcust-countries-opts');
        var optsR = document.getElementById('gcust-regions-opts');
        if (optsC) optsC.style.display = state.dataset === 'countries' ? '' : 'none';
        if (optsR) optsR.style.display = state.dataset === 'regions'   ? '' : 'none';
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

    /* ── Init ──────────────────────────────────────────────── */

    function init() {
        // Type tabs
        document.querySelectorAll('#gcust-type-tabs .gcust-tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                state.dataset = tab.getAttribute('data-type');
                _syncTypeTabs();
            });
        });

        // Continent pills
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
    }

    /* ── Public API ────────────────────────────────────────── */
    return {
        getState:        getState,
        getApiDataset:   getApiDataset,
        buildApiParams:  buildApiParams,
        isSubnational:   isSubnational,
        togglePanel:     togglePanel,
        openModal:       openModal,
        closeModal:      closeModal,
        init:            init,
        REGION_DATASETS: REGION_DATASETS,
    };
}());

document.addEventListener('DOMContentLoaded', function () { GeoCustomize.init(); });
