/* ============================================================
   GeoFreak — Relief Game Engine
   "Rocas y agua" map challenge for landform features.
   Modes: type (name it) | click (locate it on the map)
   ============================================================ */

var ReliefGame = (function () {
    "use strict";

    var map;
    var featureMarkers = {};   // id → L.circleMarker
    var featuresData   = {};   // id → feature object
    var targetIds      = [];
    var targetSet, correctSet, failedSet;
    var selectedId     = null;
    var mode, category;
    var inputEl        = null;
    var answerIndex    = {};    // normalizedName → id

    /* Locate mode state */
    var locateQueue       = [];
    var locateTarget      = null;
    var locateTempMarkers = [];
    var LOCATE_KM         = 400;   // acceptance radius in km

    /* ── Type colors ──────────────────────────────────── */
    var TYPE_COLORS = {
        mountain:       "#8B4513", volcano:        "#DC143C",
        mountain_range: "#A0522D", lake:           "#1E90FF",
        river:          "#4169E1", desert:         "#DAA520",
        valley:         "#228B22", canyon:         "#CD853F",
        plateau:        "#BC8F8F", glacier:        "#87CEEB",
        waterfall:      "#00CED1", peninsula:      "#3CB371",
        cape:           "#2E8B57", island:         "#20B2AA",
        plain:          "#9ACD32", strait:         "#4682B4",
    };

    /* ── Init ─────────────────────────────────────────── */
    function init() {
        GeoGame.init({ onStart: loadData, delayTimer: true });
        document.addEventListener("keydown", function (e) {
            if (e.key === "Enter" && inputEl) submitAnswer();
        });
    }

    /* ── Spinner ──────────────────────────────────────── */
    function showSpinner() {
        var el = document.getElementById("game-map");
        if (!el) return;
        var sp = document.createElement("div");
        sp.id = "map-spinner";
        sp.className = "map-spinner-overlay";
        sp.innerHTML = '<div class="map-spinner"></div>';
        el.appendChild(sp);
    }
    function hideSpinner() {
        var sp = document.getElementById("map-spinner");
        if (sp) sp.remove();
    }

    /* ── Read config from hidden inputs ───────────────── */
    function readSettings() {
        mode     = (document.getElementById("relief-mode-value")     || {}).value || "type";
        category = (document.getElementById("relief-category-value") || {}).value || "all";
        var continent     = (document.getElementById("relief-continent-value")      || {}).value || "all";
        var countryFilter = (document.getElementById("relief-country-filter-value") || {}).value || "";

        var url = "/api/relief-game/data?category=" + encodeURIComponent(category);
        if (continent && continent !== "all") url += "&continent=" + encodeURIComponent(continent);
        if (countryFilter) url += "&country_filter=" + encodeURIComponent(countryFilter);

        return { dataUrl: url, continent: continent };
    }

    /* ── Load data & start ────────────────────────────── */
    function loadData() {
        var s = readSettings();

        var locatePrompt = document.getElementById("relief-locate-prompt");
        var inputBar     = document.getElementById("game-input-bar");

        if (mode === "click") {
            if (locatePrompt) locatePrompt.style.display = "flex";
            if (inputBar)     inputBar.style.display     = "none";
            inputEl = null;
        } else {
            if (locatePrompt) locatePrompt.style.display = "none";
            if (inputBar)     inputBar.style.display     = "";
            inputEl = document.getElementById("answer-input-name");
            if (inputEl) inputEl.placeholder = T["rc.ph_type"] || "";
        }

        GeoGame.beginPlay();
        showSpinner();

        fetch(s.dataUrl)
            .then(function (r) { return r.json(); })
            .then(function (features) {
                setupEntities(features);
                GeoGame.setTotal(targetSet.size);

                // Dynamic timer
                var N = targetSet.size;
                if (GeoGame.settings.timeLimit > 0) {
                    var defs = (window.GAME_CONFIG && window.GAME_CONFIG.defaults) || {};
                    var secsType  = defs.secs_per_item_type  || 4;
                    var secsClick = defs.secs_per_item_click || 8;
                    var factor  = (mode === "type") ? secsType : secsClick;
                    var minutes = Math.floor(N * factor / 60) + 1;
                    var secs = minutes * 60;
                    GeoGame.settings.timeLimit = secs;
                    GeoGame.timeRemaining      = secs;
                    GeoGame._updateTimer();
                }

                initMap(s.continent);
                initMarkers(features);
                hideSpinner();
                GeoGame.startTimer();

                if (mode === "type" && inputEl) {
                    inputEl.focus();
                    updateRevealButton();
                } else if (mode === "click") {
                    startLocate();
                }
            })
            .catch(function (err) {
                hideSpinner();
                console.error("ReliefGame loadData error:", err);
            });
    }

    /* ── Entity setup ─────────────────────────────────── */
    function setupEntities(features) {
        featureMarkers = {};
        featuresData   = {};
        targetIds      = [];
        targetSet      = new Set();
        correctSet     = new Set();
        failedSet      = new Set();
        answerIndex    = {};
        selectedId     = null;

        features.forEach(function (f) {
            featuresData[f.id] = f;
            targetIds.push(f.id);
            targetSet.add(f.id);

            getNames(f).forEach(function (n) {
                if (!answerIndex[n]) answerIndex[n] = f.id;
            });
        });
    }

    function getNames(f) {
        var ns = new Set();
        if (f.name)    ns.add(GeoUtils.normalize(f.name));
        if (f.name_en) ns.add(GeoUtils.normalize(f.name_en));
        if (f.name_es) ns.add(GeoUtils.normalize(f.name_es));
        if (f.name_fr) ns.add(GeoUtils.normalize(f.name_fr));
        if (f.name_it) ns.add(GeoUtils.normalize(f.name_it));
        if (f.name_ru) ns.add(GeoUtils.normalize(f.name_ru));
        ns.delete("");
        return ns;
    }

    function getLabel(f) {
        var lang = window.LANG || "en";
        return f["name_" + lang] || f.name_en || f.name;
    }

    /* ── Map init ─────────────────────────────────────── */
    function initMap(continent) {
        var cfg = { center: [20, 0], zoom: 2, minZoom: 2 };
        var CONT = {
            europe:          { center: [54,  15], zoom: 4, minZoom: 3 },
            asia:            { center: [35,  90], zoom: 3, minZoom: 2 },
            africa:          { center: [ 5,  20], zoom: 3, minZoom: 2 },
            north_america:   { center: [48, -100], zoom: 3, minZoom: 2 },
            central_america: { center: [15, -85],  zoom: 5, minZoom: 4 },
            south_america:   { center: [-18, -58], zoom: 3, minZoom: 2 },
            oceania:         { center: [-25, 145], zoom: 4, minZoom: 3 },
        };
        if (continent && continent !== "all" && CONT[continent]) cfg = CONT[continent];

        map = L.map("game-map", {
            center: cfg.center, zoom: cfg.zoom,
            minZoom: cfg.minZoom || 2, maxZoom: 14,
            zoomControl: true, worldCopyJump: true,
        });

        L.tileLayer(
            "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
            { attribution: "&copy; OpenTopoMap", maxZoom: 17 }
        ).addTo(map);

        map.on("click", function (e) {
            if (mode === "click") {
                onMapClickLocate(e);
            }
        });
    }

    /* ── Markers ──────────────────────────────────────── */
    function initMarkers(features) {
        features.forEach(function (f) {
            var color = TYPE_COLORS[f.type] || "#999";
            var marker = L.circleMarker([f.lat, f.lon], markerStyle(f.id, color));
            marker._typeColor = color;

            marker.on("click", function (e) {
                L.DomEvent.stopPropagation(e);
                if (mode === "type") onClickMarker(f.id);
            });

            marker.addTo(map);
            featureMarkers[f.id] = marker;
        });
    }

    function markerStyle(id, color) {
        if (failedSet && failedSet.has(id))  return { radius: 7, fillColor: "#ef5350", color: "#c62828", weight: 1.5, fillOpacity: 0.85 };
        if (correctSet && correctSet.has(id)) return { radius: 7, fillColor: "#4caf50", color: "#2e7d32", weight: 1.5, fillOpacity: 0.9 };
        if (selectedId === id)               return { radius: 8, fillColor: "#1a73e8", color: "#0d47a1", weight: 2,   fillOpacity: 0.8 };
        if (targetSet && targetSet.has(id))  return { radius: 5, fillColor: color || "#78909c", color: "#455a64", weight: 1, fillOpacity: 0.6 };
        return { radius: 4, fillColor: "#cfd8dc", color: "#b0bec5", weight: 0.5, fillOpacity: 0.4 };
    }

    function refreshMarker(id) {
        var m = featureMarkers[id];
        if (m) m.setStyle(markerStyle(id, m._typeColor));
    }

    /* ── Click on marker (type mode) ──────────────────── */
    function onClickMarker(id) {
        if (correctSet.has(id) || failedSet.has(id)) {
            showTooltip(id, 2500);
            return;
        }
        if (!targetSet.has(id)) return;
        var prev = selectedId;
        selectedId = id;
        if (prev && prev !== id) refreshMarker(prev);
        refreshMarker(id);
        updateRevealButton();
    }

    /* ── Tooltip ──────────────────────────────────────── */
    var _tooltipTimer = null;
    function showTooltip(id, duration) {
        if (_tooltipTimer) { clearTimeout(_tooltipTimer); _tooltipTimer = null; }
        Object.keys(featureMarkers).forEach(function (mid) {
            try { featureMarkers[mid].closeTooltip(); featureMarkers[mid].unbindTooltip(); } catch(e){}
        });
        var m = featureMarkers[id], f = featuresData[id];
        if (!m || !f) return;
        m.bindTooltip(getLabel(f), { permanent: true, className: "reveal-tooltip", direction: "top" }).openTooltip();
        if (duration) {
            _tooltipTimer = setTimeout(function () {
                try { m.closeTooltip(); m.unbindTooltip(); } catch(e){}
                _tooltipTimer = null;
            }, duration);
        }
    }

    /* ── Reveal button ────────────────────────────────── */
    function updateRevealButton() {
        if (mode !== "type") return;
        var btn = document.getElementById("btn-reveal-bar");
        if (btn) btn.disabled = !selectedId;
    }

    /* ── Submit answer ────────────────────────────────── */
    function submitAnswer() {
        if (!inputEl) return;
        var answer = GeoUtils.normalize(inputEl.value.trim());
        if (!answer) return;
        submitType(answer);
    }

    function submitType(answer) {
        var id = answerIndex[answer];
        if (id && targetSet.has(id) && !correctSet.has(id) && !failedSet.has(id)) {
            markCorrect(id);
            if (selectedId === id) { selectedId = null; updateRevealButton(); }
            flashInput(inputEl, true);
            if (inputEl) { inputEl.value = ""; inputEl.focus(); }
            showTypeFeedback(true, featuresData[id]);
            checkComplete();
        } else {
            flashInput(inputEl, false);
            showTypeFeedback(false);
        }
    }

    /* ── Mark correct / failed ────────────────────────── */
    function markCorrect(id) {
        correctSet.add(id);
        GeoGame.addCorrect();
        refreshMarker(id);
    }
    function markFailed(id) {
        failedSet.add(id);
        refreshMarker(id);
    }
    function checkComplete() {
        if ((correctSet.size + failedSet.size) >= targetSet.size) {
            setTimeout(function () { GeoGame.endGame(); }, 600);
        }
    }

    /* ── Type feedback ────────────────────────────────── */
    function flashInput(el, success) {
        if (!el) return;
        var cls = success ? "correct-flash" : "wrong-flash";
        el.classList.add(cls);
        setTimeout(function () { el.classList.remove(cls); }, success ? 600 : 400);
    }
    function showTypeFeedback(ok, f) {
        var el = document.getElementById("input-feedback");
        if (!el) return;
        if (ok && f) {
            el.className = "input-feedback correct";
            el.textContent = "\u2705 " + getLabel(f);
        } else {
            el.className = "input-feedback wrong";
            el.textContent = T["js.no_match"] || "\u274C No match";
        }
        clearTimeout(el._timer);
        el._timer = setTimeout(function () {
            el.className = "input-feedback";
            el.textContent = "";
        }, 1500);
    }

    /* ── Reveal ───────────────────────────────────────── */
    function reveal() {
        if (mode === "click") return;
        if (!selectedId) return;
        var id = selectedId;
        var f = featuresData[id];
        if (!f) return;
        markFailed(id);
        var label = getLabel(f);
        var el = document.getElementById("input-feedback");
        if (el) {
            el.className = "input-feedback wrong";
            el.textContent = (T["js.revealed"] || "\uD83D\uDC41\uFE0F {name}").replace("{name}", label);
            clearTimeout(el._timer);
            el._timer = setTimeout(function () { el.className = "input-feedback"; el.textContent = ""; }, 2000);
        }
        showTooltip(id, 2000);
        selectedId = null;
        updateRevealButton();
        checkComplete();
    }

    /* ── Locate mode ──────────────────────────────────── */
    function startLocate() {
        locateQueue = GeoUtils.shuffle(targetIds.slice());
        locateTempMarkers = [];
        advanceLocate();
    }

    function advanceLocate() {
        locateTempMarkers.forEach(function (m) { map.removeLayer(m); });
        locateTempMarkers = [];

        if (locateQueue.length === 0) { checkComplete(); return; }
        locateTarget = featuresData[locateQueue.shift()];
        if (!locateTarget) { advanceLocate(); return; }

        var promptEl = document.getElementById("relief-locate-text");
        if (promptEl) promptEl.textContent = getLabel(locateTarget) + "  \u2192  ?";
        var bar = document.getElementById("relief-locate-prompt");
        if (bar) bar.style.display = "flex";
    }

    function onMapClickLocate(e) {
        if (!locateTarget) return;
        var f = locateTarget;
        var targetLL = L.latLng(f.lat, f.lon);
        var clickLL  = e.latlng;
        var distKm   = clickLL.distanceTo(targetLL) / 1000;
        var correct  = distKm <= LOCATE_KM;

        // Click dot
        var dot = L.circleMarker(clickLL, {
            radius: 6, fillColor: correct ? "#4caf50" : "#ef5350",
            color: correct ? "#2e7d32" : "#c62828", weight: 2, fillOpacity: 0.9,
        }).addTo(map);
        locateTempMarkers.push(dot);

        if (!correct) {
            var actual = L.circleMarker(targetLL, {
                radius: 8, fillColor: "#ff9800", color: "#e65100", weight: 2, fillOpacity: 0.9,
            }).addTo(map);
            locateTempMarkers.push(actual);
            var line = L.polyline([clickLL, targetLL], { color: "#ff9800", weight: 1.5, dashArray: "4,4" }).addTo(map);
            locateTempMarkers.push(line);
        }

        if (correct) markCorrect(f.id);
        else markFailed(f.id);

        var promptEl = document.getElementById("relief-locate-text");
        if (promptEl) {
            var distStr = Math.round(distKm) + " km";
            promptEl.textContent = correct
                ? "\u2705 " + getLabel(f) + " (" + distStr + ")"
                : "\u274C " + getLabel(f) + " \u2014 " + distStr;
        }

        locateTarget = null;
        setTimeout(function () { advanceLocate(); checkComplete(); }, 1600);
    }

    return { init: init, submitAnswer: submitAnswer, reveal: reveal };
})();
