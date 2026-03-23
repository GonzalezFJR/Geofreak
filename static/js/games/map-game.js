/* ============================================================
   GeoFreak — Map Game Engine
   Shared by all 4 map-based games.
   Config: { mode: "click"|"type",  target: "country"|"capital" }
   ============================================================ */

var MapGame = (function () {
    var map, geojsonLayer;
    var countryLayers = {};   // iso3 → Leaflet layer
    var countriesData = {};   // iso3 → country object
    var targetIsos    = [];   // ISOs in the game
    var targetSet     = null; // Set<iso3>
    var correctSet    = null; // Set<iso3>
    var failedSet     = null; // Set<iso3> — revealed (wrong)
    var selectedIso   = null;
    var mode, target;

    /* ── Answers lookup ────────────────────────────────────── */
    // For "type" mode: maps normalised answer → iso3
    var answerIndex = {};

    /**
     * @param {Object} config
     *   mode:   "click" | "type"
     *   target: "country" | "capital"
     */
    function init(config) {
        mode   = config.mode;
        target = config.target;
        GeoGame.init({ onStart: loadData });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') submitAnswer();
        });
    }

    /* ── Data loading ──────────────────────────────────────── */
    function loadData(settings) {
        Promise.all([
            fetch('/api/countries').then(function (r) { return r.json(); }),
            fetch('/api/geojson/all').then(function (r) { return r.json(); }),
        ]).then(function (res) {
            var countries = res[0];
            var geojson   = res[1];

            // Index by iso3
            countries.forEach(function (c) {
                if (c.iso_a3) countriesData[c.iso_a3] = c;
            });

            // Filter by continent
            var filtered = GeoUtils.filterByContinent(countries, settings.continent);
            // For capital games, only include countries with a known capital
            filtered = filtered.filter(function (c) {
                if (!c.iso_a3 || !c.name) return false;
                if (target === 'capital') return c.capital && c.capital.length > 0;
                return true;
            });

            targetSet   = new Set();
            correctSet  = new Set();
            failedSet   = new Set();
            targetIsos  = [];
            answerIndex = {};

            filtered.forEach(function (c) {
                targetSet.add(c.iso_a3);
                targetIsos.push(c.iso_a3);

                // Build answer index for "type" mode
                var names = target === 'capital'
                    ? GeoUtils.getCapitalNames(c)
                    : GeoUtils.getCountryNames(c);
                names.forEach(function (n) {
                    answerIndex[n] = c.iso_a3;
                });
            });

            GeoGame.setTotal(targetSet.size);

            initMap(geojson);

            // Focus input in type mode
            if (mode === 'type') {
                var inp = document.getElementById('answer-input');
                if (inp) inp.focus();
            }
        });
    }

    /* ── Map initialisation ────────────────────────────────── */
    function initMap(geojson) {
        map = L.map('game-map', {
            center: [20, 0],
            zoom: 2,
            minZoom: 2,
            maxZoom: 10,
            zoomControl: true,
            worldCopyJump: true,
        });

        L.tileLayer(
            'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
            { attribution: '© CARTO', subdomains: 'abcd' }
        ).addTo(map);

        geojsonLayer = L.geoJSON(geojson, {
            style: function (f) { return styleFor(f); },
            onEachFeature: function (f, layer) {
                var iso3 = GeoUtils.getIso3(f);
                if (!iso3 || iso3 === '-99') return;
                countryLayers[iso3] = layer;

                if (mode === 'click') {
                    layer.on('click', function () { onClickCountry(iso3); });
                }

                layer.on('mouseover', function () {
                    if (targetSet.has(iso3) && !correctSet.has(iso3)) {
                        layer.setStyle({ fillOpacity: 0.5 });
                    }
                });
                layer.on('mouseout', function () {
                    geojsonLayer.resetStyle(layer);
                });
            },
        }).addTo(map);
    }

    /* ── Styling ───────────────────────────────────────────── */
    function styleFor(feature) {
        var iso3 = GeoUtils.getIso3(feature);
        if (failedSet && failedSet.has(iso3)) {
            return { fillColor: '#ef5350', fillOpacity: 0.55, color: '#c62828', weight: 1.5 };
        }
        if (correctSet && correctSet.has(iso3)) {
            return { fillColor: '#4caf50', fillOpacity: 0.6, color: '#2e7d32', weight: 1.5 };
        }
        if (selectedIso === iso3) {
            return { fillColor: '#1a73e8', fillOpacity: 0.45, color: '#0d47a1', weight: 2 };
        }
        if (targetSet && targetSet.has(iso3)) {
            return { fillColor: '#e2e8f0', fillOpacity: 0.5, color: '#94a3b8', weight: 1 };
        }
        // Non-target
        return { fillColor: '#f1f5f9', fillOpacity: 0.25, color: '#cbd5e1', weight: 0.5 };
    }

    function refreshStyle(iso3) {
        var layer = countryLayers[iso3];
        if (layer) {
            var f = layer.feature || (layer.getLayers && layer.getLayers()[0] && layer.getLayers()[0].feature);
            if (f) layer.setStyle(styleFor(f));
        }
    }

    /* ── Click mode ────────────────────────────────────────── */
    function onClickCountry(iso3) {
        if (!targetSet.has(iso3) || correctSet.has(iso3) || failedSet.has(iso3)) return;

        // Deselect previous
        if (selectedIso && selectedIso !== iso3) refreshStyle(selectedIso);

        selectedIso = iso3;
        refreshStyle(iso3);

        var prompt = document.getElementById('game-prompt');
        prompt.style.display = 'flex';

        var ptxt = document.getElementById('prompt-text');
        var pcountry = document.getElementById('prompt-country');

        if (target === 'capital') {
            var cData = countriesData[iso3];
            if (pcountry) pcountry.textContent = cData ? cData.name : '';
            if (ptxt)     ptxt.textContent = T['mg.what_capital'] || '¿Capital?';
        } else {
            if (pcountry) pcountry.textContent = '';
            if (ptxt)     ptxt.textContent = T['mg.what_country'] || 'What country is this?';
        }

        var input = document.getElementById('answer-input');
        input.value = '';
        input.focus();
    }

    /* ── Submit answer ─────────────────────────────────────── */
    function submitAnswer() {
        var input = document.getElementById('answer-input');
        var answer = GeoUtils.normalize(input.value.trim());
        if (!answer) return;

        if (mode === 'click') {
            submitClick(answer, input);
        } else {
            submitType(answer, input);
        }
    }

    function submitClick(answer, input) {
        if (!selectedIso) return;
        var c = countriesData[selectedIso];
        if (!c) return;

        var acceptable = target === 'capital'
            ? GeoUtils.getCapitalNames(c)
            : GeoUtils.getCountryNames(c);

        if (acceptable.has(answer)) {
            markCorrect(selectedIso);
            input.value = '';
            var prompt = document.getElementById('game-prompt');
            prompt.style.display = 'none';
            selectedIso = null;
            checkComplete();
        } else {
            flashInput(input, false);
        }
    }

    function submitType(answer, input) {
        var iso3 = answerIndex[answer];
        if (iso3 && targetSet.has(iso3) && !correctSet.has(iso3) && !failedSet.has(iso3)) {
            markCorrect(iso3);
            flashInput(input, true);
            input.value = '';
            input.focus();
            showTypeFeedback(true, countriesData[iso3]);
            checkComplete();
        } else {
            flashInput(input, false);
            showTypeFeedback(false);
        }
    }

    function markCorrect(iso3) {
        correctSet.add(iso3);
        GeoGame.addCorrect();
        refreshStyle(iso3);
    }

    function checkComplete() {
        if ((correctSet.size + failedSet.size) >= targetSet.size) {
            setTimeout(function () { GeoGame.endGame(); }, 600);
        }
    }

    function flashInput(input, success) {
        var cls = success ? 'correct-flash' : 'wrong-flash';
        input.classList.add(cls);
        setTimeout(function () { input.classList.remove(cls); }, success ? 600 : 400);
    }

    function showTypeFeedback(ok, country) {
        var el = document.getElementById('input-feedback');
        if (!el) return;
        if (ok && country) {
            var label = target === 'capital'
                ? '✅ ' + country.capital + ' → ' + country.name
                : '✅ ' + country.name;
            el.className = 'input-feedback correct';
            el.textContent = label;
        } else if (!ok) {
            el.className = 'input-feedback wrong';
            el.textContent = T['js.no_match'] || '❌ No match';
        }
        clearTimeout(el._timer);
        el._timer = setTimeout(function () {
            el.className = 'input-feedback';
            el.textContent = '';
        }, 1500);
    }

    /* ── Reveal (Desvelar) ─────────────────────────────────── */
    function markFailed(iso3) {
        failedSet.add(iso3);
        refreshStyle(iso3);
    }

    function reveal() {
        if (mode === 'click') {
            revealClick();
        } else {
            revealType();
        }
    }

    function revealClick() {
        if (!selectedIso) return;
        var c = countriesData[selectedIso];
        if (!c) return;

        var answer = target === 'capital' ? c.capital : c.name;
        var input = document.getElementById('answer-input');
        input.value = answer;
        markFailed(selectedIso);

        // Show tooltip on the country
        var layer = countryLayers[selectedIso];
        if (layer) {
            var label = target === 'capital' ? c.capital : c.name;
            layer.bindTooltip(label, { permanent: true, className: 'reveal-tooltip', direction: 'center' }).openTooltip();
        }

        var prompt = document.getElementById('game-prompt');
        setTimeout(function () {
            prompt.style.display = 'none';
            selectedIso = null;
            checkComplete();
        }, 1500);
    }

    function revealType() {
        // Reveal a random remaining country
        var remaining = [];
        targetIsos.forEach(function (iso) {
            if (!correctSet.has(iso) && !failedSet.has(iso)) remaining.push(iso);
        });
        if (remaining.length === 0) return;
        var iso3 = remaining[Math.floor(Math.random() * remaining.length)];
        var c = countriesData[iso3];
        if (!c) return;

        markFailed(iso3);

        var label = target === 'capital' ? (c.capital + ' → ' + c.name) : c.name;
        showTypeFeedback(false);
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

        // Show tooltip on the country
        var layer = countryLayers[iso3];
        if (layer) {
            layer.bindTooltip(target === 'capital' ? c.capital : c.name, { permanent: true, className: 'reveal-tooltip', direction: 'center' }).openTooltip();
        }

        checkComplete();
    }

    return { init: init, submitAnswer: submitAnswer, reveal: reveal };
})();
