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

    // ─── SVG icon paths ──────────────────────────────────────────────
    var ICON_BASE = "/static/img/icons/relief/";

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
    var terrainCleanLayer = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}",
        { attribution: "&copy; Esri", maxZoom: 8 }
    );
    var blankLayer = L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
        { attribution: "&copy; CARTO", subdomains: "abcd", maxZoom: 19 }
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
    tileLayers[T["relief.layer_terrain_clean"] || "Terrain (clean)"] = terrainCleanLayer;
    tileLayers[T["relief.layer_blank"] || "Blank"] = blankLayer;
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
    var geojsonLoading = {};             // wikidata_id → true (currently fetching)
    var GEOJSON_BASE = "/static/data/relief_geojson/";
    var filteredFeatures = [];           // features that pass current filters

    // ─── SVG icon creation for markers ──────────────────────────────
    function createSvgIcon(type) {
        return L.divIcon({
            className: "relief-svg-icon",
            html: '<img src="' + ICON_BASE + type + '.svg" width="20" height="20" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,0.3))">',
            iconSize: [20, 20],
            iconAnchor: [10, 10],
            popupAnchor: [0, -12],
        });
    }

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

    // ─── Marker creation (SVG icon) ─────────────────────────────────
    function createIconMarker(f) {
        var icon = createSvgIcon(f.type);
        var marker = L.marker([f.lat, f.lon], { icon: icon });
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        marker.bindPopup(popupHtml(f));
        marker.bindTooltip(displayName, {
            direction: "top", offset: [0, -12],
            className: "country-tooltip-wrapper",
        });
        marker._featureData = f;
        return marker;
    }

    // ─── GeoJSON shape creation ──────────────────────────────────────
    function createGeoJsonLayer(f, geojson) {
        var color = TYPE_COLORS[f.type] || "#999";
        var isLine = (geojson.type === "LineString" || geojson.type === "MultiLineString");
        var isRiver = (f.type === "river");
        var baseStyle;

        if (isRiver) {
            // Brush-stroke style for rivers
            baseStyle = {
                color: color,
                weight: 4,
                opacity: 0.55,
                lineCap: "round",
                lineJoin: "round",
                fillOpacity: 0,
            };
        } else if (isLine) {
            baseStyle = {
                color: color,
                weight: 3,
                opacity: 0.8,
                lineCap: "round",
                lineJoin: "round",
                fillOpacity: 0,
            };
        } else {
            // Polygons: thicker outline for better hover/click target
            baseStyle = {
                color: color,
                weight: 2.5,
                opacity: 0.8,
                fillColor: color,
                fillOpacity: 0.2,
            };
        }

        var layer = L.geoJSON(geojson, { style: baseStyle });
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        layer.bindPopup(popupHtml(f));
        layer.bindTooltip(displayName, {
            sticky: true,
            className: "country-tooltip-wrapper",
        });
        layer._featureData = f;

        // Hover effect for polygons and lines
        layer.eachLayer(function (sub) {
            sub.on("mouseover", function () {
                sub.setStyle({
                    weight: isRiver ? 6 : (isLine ? 4.5 : 4),
                    opacity: 1,
                    fillOpacity: isLine ? 0 : 0.35,
                });
            });
            sub.on("mouseout", function () {
                sub.setStyle(baseStyle);
            });
        });

        return layer;
    }

    // ─── Filtering & rebuilding ──────────────────────────────────────
    function getFilteredFeatures() {
        var q = searchQuery.toLowerCase();
        var result = [];
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
            result.push(f);
        }
        return result;
    }

    function rebuildMarkers() {
        markers.clearLayers();
        geoJsonLayer.clearLayers();
        filteredFeatures = getFilteredFeatures();

        // All features as SVG icon markers in cluster group
        for (var i = 0; i < filteredFeatures.length; i++) {
            markers.addLayer(createIconMarker(filteredFeatures[i]));
        }

        // If any features should show GeoJSON at current zoom, overlay them
        showGeoJsonInView();

        var countEl = document.getElementById("relief-count");
        if (countEl) countEl.textContent = filteredFeatures.length + " / " + allFeatures.length;
    }

    // ─── Lazy GeoJSON loading ────────────────────────────────────────
    function showGeoJsonInView() {
        geoJsonLayer.clearLayers();
        var currentZoom = map.getZoom();
        var bounds = map.getBounds();
        var toFetch = [];

        for (var i = 0; i < filteredFeatures.length; i++) {
            var f = filteredFeatures[i];
            if (!f.has_geojson) continue;
            if (currentZoom < f.min_zoom) continue;
            if (!bounds.contains([f.lat, f.lon])) continue;

            var cached = geojsonCache[f.wikidata_id];
            if (cached) {
                geoJsonLayer.addLayer(createGeoJsonLayer(f, cached));
            } else if (!geojsonLoading[f.wikidata_id]) {
                toFetch.push(f);
            }
        }

        if (toFetch.length > 0) {
            fetchGeoJsonBatch(toFetch);
        }
    }

    function fetchGeoJsonBatch(features) {
        var batchSize = 20;
        var batch = features.slice(0, batchSize);
        batch.forEach(function (f) { geojsonLoading[f.wikidata_id] = true; });

        Promise.all(batch.map(function (f) {
            return fetch(GEOJSON_BASE + f.wikidata_id + ".geojson")
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) {
                    delete geojsonLoading[f.wikidata_id];
                    if (data && data.geometry) {
                        geojsonCache[f.wikidata_id] = data.geometry;
                    }
                })
                .catch(function () { delete geojsonLoading[f.wikidata_id]; });
        })).then(function () {
            showGeoJsonInView();
            var remaining = features.slice(batchSize);
            if (remaining.length > 0) {
                fetchGeoJsonBatch(remaining);
            }
        });
    }

    // ─── Map zoom/move handler ──────────────────────────────────────
    var viewTimer = null;
    map.on("moveend", function () {
        clearTimeout(viewTimer);
        viewTimer = setTimeout(function () {
            showGeoJsonInView();
        }, 200);
    });

    // ─── Legend ──────────────────────────────────────────────────────
    function addLegend() {
        var types = Object.keys(TYPE_COLORS);
        var legend = L.control({ position: "bottomleft" });
        legend.onAdd = function () {
            var div = L.DomUtil.create("div", "relief-legend");
            types.forEach(function (t) {
                var label = typeLabel(t);
                div.innerHTML += '<div class="relief-legend-item">' +
                    '<img src="' + ICON_BASE + t + '.svg" class="relief-legend-icon" width="14" height="14">' +
                    '<span>' + label + '</span></div>';
            });
            L.DomEvent.disableClickPropagation(div);
            return div;
        };
        legend.addTo(map);
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

            var badge = document.createElement("img");
            badge.src = ICON_BASE + type + ".svg";
            badge.width = 16;
            badge.height = 16;
            badge.className = "relief-filter-icon";

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
            openBtn.classList.add("visible");
        });
    }
    if (openBtn) {
        openBtn.addEventListener("click", function () {
            panel.classList.remove("collapsed");
            openBtn.classList.remove("visible");
        });
    }

    // ─── Init ──────────────────────────────────────────────────────────
    async function init() {
        var loading = document.getElementById("loading");
        try {
            var resp = await fetch("/api/relief-features");
            allFeatures = await resp.json();

            // No GeoJSON preloading — loaded lazily on zoom/pan
            addLegend();
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
