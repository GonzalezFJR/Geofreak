(function () {
    "use strict";

    // ─── Color palette by feature type ─────────────────────────────────
    var TYPE_COLORS = {
        volcano:        "#DC143C",
        waterfall:      "#00CED1",
        glacier:        "#87CEEB",
        canyon:         "#CD853F",
        strait:         "#4682B4",
        cape:           "#2E8B57",
        peninsula:      "#3CB371",
        island:         "#20B2AA",
        desert:         "#DAA520",
        plateau:        "#BC8F8F",
        plain:          "#9ACD32",
        valley:         "#228B22",
        mountain_range: "#A0522D",
        mountain:       "#8B4513",
        lake:           "#1E90FF",
        river:          "#4169E1",
    };

    // Translated type labels (keyed by type, value per lang)
    var TYPE_LABELS = {
        mountain:       { es: "Montaña",      en: "Mountain",       fr: "Montagne",     it: "Montagna",     ru: "Гора" },
        volcano:        { es: "Volcán",        en: "Volcano",        fr: "Volcan",       it: "Vulcano",      ru: "Вулкан" },
        mountain_range: { es: "Cordillera",    en: "Mountain range", fr: "Chaîne",       it: "Catena",       ru: "Хребет" },
        lake:           { es: "Lago",          en: "Lake",           fr: "Lac",          it: "Lago",         ru: "Озеро" },
        river:          { es: "Río",           en: "River",          fr: "Fleuve",       it: "Fiume",        ru: "Река" },
        desert:         { es: "Desierto",      en: "Desert",         fr: "Désert",       it: "Deserto",      ru: "Пустыня" },
        valley:         { es: "Valle",         en: "Valley",         fr: "Vallée",       it: "Valle",        ru: "Долина" },
        canyon:         { es: "Cañón",         en: "Canyon",         fr: "Canyon",       it: "Canyon",       ru: "Каньон" },
        plateau:        { es: "Meseta",        en: "Plateau",        fr: "Plateau",      it: "Altopiano",    ru: "Плато" },
        glacier:        { es: "Glaciar",       en: "Glacier",        fr: "Glacier",      it: "Ghiacciaio",   ru: "Ледник" },
        waterfall:      { es: "Cascada",       en: "Waterfall",      fr: "Cascade",      it: "Cascata",      ru: "Водопад" },
        peninsula:      { es: "Península",     en: "Peninsula",      fr: "Péninsule",    it: "Penisola",     ru: "Полуостров" },
        cape:           { es: "Cabo",          en: "Cape",           fr: "Cap",          it: "Capo",         ru: "Мыс" },
        island:         { es: "Isla",          en: "Island",         fr: "Île",          it: "Isola",        ru: "Остров" },
        plain:          { es: "Llanura",       en: "Plain",          fr: "Plaine",       it: "Pianura",      ru: "Равнина" },
        strait:         { es: "Estrecho",      en: "Strait",         fr: "Détroit",      it: "Stretto",      ru: "Пролив" },
    };

    var LANG = window.LANG || "en";

    function typeLabel(type) {
        var labels = TYPE_LABELS[type];
        return labels ? (labels[LANG] || labels.en || type) : type.replace(/_/g, " ");
    }

    // ─── Map setup ─────────────────────────────────────────────────────
    var map = L.map("map", {
        center: [20, 0],
        zoom: 3,
        minZoom: 2,
        maxZoom: 18,
        zoomControl: true,
        worldCopyJump: true,
    });

    var T = window.T || {};

    var terrainLayer = L.tileLayer(
        "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        { attribution: "&copy; OpenTopoMap", maxZoom: 17 }
    );
    var satelliteLayer = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { attribution: "&copy; Esri", maxZoom: 18 }
    );
    var standardLayer = L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        { attribution: "&copy; OpenStreetMap", maxZoom: 19 }
    );

    var tileLayers = {};
    tileLayers[T["relief.layer_terrain"] || "Terrain"] = terrainLayer;
    tileLayers[T["relief.layer_satellite"] || "Satellite"] = satelliteLayer;
    tileLayers[T["relief.layer_standard"] || "Standard"] = standardLayer;

    terrainLayer.addTo(map);
    L.control.layers(tileLayers, null, { position: "topright", collapsed: true }).addTo(map);

    // ─── State ─────────────────────────────────────────────────────────
    var allFeatures = [];
    var markers = L.markerClusterGroup({
        maxClusterRadius: 40,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        disableClusteringAtZoom: 12,
    });
    var geoJsonLayer = L.layerGroup();   // non-clustered layer for polygons/lines
    var activeTypes = new Set(Object.keys(TYPE_COLORS));
    var searchQuery = "";
    var geojsonCache = {};               // wikidata_id → GeoJSON geometry (or null)
    var GEOJSON_BASE = "/static/data/relief_geojson/";

    // ─── Popup HTML builder ──────────────────────────────────────────
    function popupHtml(f) {
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        var tl = typeLabel(f.type);
        var html = '<div class="relief-popup">' +
            '<div class="rp-name">' + displayName + '</div>' +
            '<div class="rp-type">' + tl + '</div>';
        if (f.country_names_en)
            html += '<div class="rp-country">' + f.country_names_en + '</div>';
        if (f.elevation_m != null)
            html += '<div class="rp-stat">' + f.elevation_m.toLocaleString() + ' m</div>';
        if (f.length_km != null)
            html += '<div class="rp-stat">' + f.length_km.toLocaleString() + ' km</div>';
        if (f.area_km2 != null)
            html += '<div class="rp-stat">' + f.area_km2.toLocaleString() + ' km\u00B2</div>';
        html += '</div>';
        return html;
    }

    // ─── Marker creation (circle fallback) ───────────────────────────
    function createCircleMarker(f) {
        var color = TYPE_COLORS[f.type] || "#999";
        var marker = L.circleMarker([f.lat, f.lon], {
            radius: 6,
            fillColor: color,
            color: "#fff",
            weight: 1.5,
            opacity: 1,
            fillOpacity: 0.85,
        });
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        marker.bindPopup(popupHtml(f));
        marker.bindTooltip(displayName, {
            direction: "top", offset: [0, -8],
            className: "country-tooltip-wrapper",
        });
        marker._featureData = f;
        return marker;
    }

    // ─── GeoJSON shape creation ──────────────────────────────────────
    function createGeoJsonLayer(f, geojson) {
        var color = TYPE_COLORS[f.type] || "#999";
        var isLine = (geojson.type === "LineString" || geojson.type === "MultiLineString");
        var layer = L.geoJSON(geojson, {
            style: {
                color: color,
                weight: isLine ? 2.5 : 1.5,
                opacity: 0.9,
                fillColor: color,
                fillOpacity: isLine ? 0 : 0.25,
            },
        });
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        layer.bindPopup(popupHtml(f));
        layer.bindTooltip(displayName, {
            sticky: true,
            className: "country-tooltip-wrapper",
        });
        layer._featureData = f;
        return layer;
    }

    // ─── Filtering ─────────────────────────────────────────────────────
    function rebuildMarkers() {
        markers.clearLayers();
        geoJsonLayer.clearLayers();
        var count = 0;
        var q = searchQuery.toLowerCase();

        for (var i = 0; i < allFeatures.length; i++) {
            var f = allFeatures[i];
            if (!activeTypes.has(f.type)) continue;
            if (q) {
                var match = (f.name || "").toLowerCase().indexOf(q) >= 0 ||
                    (f.name_es || "").toLowerCase().indexOf(q) >= 0 ||
                    (f.name_en || "").toLowerCase().indexOf(q) >= 0 ||
                    (f.name_fr || "").toLowerCase().indexOf(q) >= 0 ||
                    (f.name_it || "").toLowerCase().indexOf(q) >= 0 ||
                    (f.name_ru || "").toLowerCase().indexOf(q) >= 0;
                if (!match) continue;
            }
            var cached = geojsonCache[f.wikidata_id];
            if (cached) {
                geoJsonLayer.addLayer(createGeoJsonLayer(f, cached));
            } else {
                markers.addLayer(createCircleMarker(f));
            }
            count++;
        }

        var countEl = document.getElementById("relief-count");
        if (countEl) countEl.textContent = count + " / " + allFeatures.length;
    }

    // ─── Filter panel ──────────────────────────────────────────────────
    function buildFilters() {
        var container = document.getElementById("relief-filters");
        if (!container) return;

        var counts = {};
        for (var i = 0; i < allFeatures.length; i++) {
            var t = allFeatures[i].type;
            counts[t] = (counts[t] || 0) + 1;
        }

        // Sort types by count descending
        var types = Object.keys(TYPE_COLORS).filter(function (t) { return counts[t]; });
        types.sort(function (a, b) { return (counts[b] || 0) - (counts[a] || 0); });

        // Select all / none controls
        var controls = document.createElement("div");
        controls.className = "relief-select-controls";
        var btnAll = document.createElement("button");
        btnAll.textContent = LANG === "es" ? "Todos" : LANG === "fr" ? "Tous" : LANG === "it" ? "Tutti" : LANG === "ru" ? "Все" : "All";
        btnAll.className = "relief-select-btn";
        btnAll.addEventListener("click", function () {
            activeTypes = new Set(Object.keys(TYPE_COLORS));
            container.querySelectorAll("input[type=checkbox]").forEach(function (cb) { cb.checked = true; });
            rebuildMarkers();
        });
        var btnNone = document.createElement("button");
        btnNone.textContent = LANG === "es" ? "Ninguno" : LANG === "fr" ? "Aucun" : LANG === "it" ? "Nessuno" : LANG === "ru" ? "Ни одного" : "None";
        btnNone.className = "relief-select-btn";
        btnNone.addEventListener("click", function () {
            activeTypes.clear();
            container.querySelectorAll("input[type=checkbox]").forEach(function (cb) { cb.checked = false; });
            rebuildMarkers();
        });
        controls.appendChild(btnAll);
        controls.appendChild(btnNone);
        container.appendChild(controls);

        types.forEach(function (type) {
            var label = document.createElement("label");
            label.className = "relief-filter-item";

            var cb = document.createElement("input");
            cb.type = "checkbox";
            cb.checked = true;
            cb.value = type;
            cb.addEventListener("change", function () {
                if (this.checked) activeTypes.add(type);
                else activeTypes.delete(type);
                rebuildMarkers();
            });

            var badge = document.createElement("span");
            badge.className = "relief-color-badge";
            badge.style.background = TYPE_COLORS[type];

            var text = document.createElement("span");
            text.textContent = typeLabel(type) + " (" + counts[type] + ")";

            label.appendChild(cb);
            label.appendChild(badge);
            label.appendChild(text);
            container.appendChild(label);
        });
    }

    // ─── Search ────────────────────────────────────────────────────────
    var searchTimer = null;
    var searchEl = document.getElementById("relief-search");
    if (searchEl) {
        searchEl.addEventListener("input", function () {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(function () {
                searchQuery = searchEl.value.trim();
                rebuildMarkers();
            }, 300);
        });
    }

    // ─── Panel toggle ──────────────────────────────────────────────────
    var panel = document.getElementById("relief-panel");
    var toggleBtn = document.getElementById("panel-toggle");
    var openBtn = document.getElementById("panel-open");

    if (toggleBtn) {
        toggleBtn.addEventListener("click", function () {
            panel.classList.add("collapsed");
            openBtn.classList.remove("hidden");
        });
    }
    if (openBtn) {
        openBtn.addEventListener("click", function () {
            panel.classList.remove("collapsed");
            openBtn.classList.add("hidden");
        });
    }

    // ─── Init ──────────────────────────────────────────────────────────
    async function init() {
        var loading = document.getElementById("loading");
        try {
            var resp = await fetch("/api/relief-features");
            allFeatures = await resp.json();

            // Preload GeoJSON for features that have them
            var toLoad = allFeatures.filter(function (f) { return f.has_geojson; });
            var batchSize = 20;
            for (var i = 0; i < toLoad.length; i += batchSize) {
                var batch = toLoad.slice(i, i + batchSize);
                await Promise.all(batch.map(function (f) {
                    return fetch(GEOJSON_BASE + f.wikidata_id + ".geojson")
                        .then(function (r) { return r.ok ? r.json() : null; })
                        .then(function (data) {
                            if (data && data.geometry) geojsonCache[f.wikidata_id] = data.geometry;
                        })
                        .catch(function () {});
                }));
            }

            buildFilters();
            rebuildMarkers();
            map.addLayer(markers);
            map.addLayer(geoJsonLayer);
        } catch (err) {
            console.error("Error loading relief data:", err);
        } finally {
            if (loading) {
                loading.classList.add("hidden");
                setTimeout(function () { loading.remove(); }, 500);
            }
        }
    }

    init();
})();
