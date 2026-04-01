/**
 * GeoFreak — Unified Interactive Map
 * Political (countries + cities) + Physical (relief features) with presets
 */

(function () {
    "use strict";
    console.log("[GeoFreak] map.js v3 loaded — circleMarker city rendering");

    var LANG = window.LANG || "en";
    var T = window.T || {};

    // ─── Map setup ──────────────────────────────────────────
    var map = L.map("map", {
        center: [20, 0],
        zoom: 3,
        minZoom: 2,
        maxZoom: 18,
        zoomControl: true,
        worldCopyJump: true,
    });

    // Custom pane for city markers — above the overlay pane (GeoJSON countries)
    map.createPane("cityPane");
    map.getPane("cityPane").style.zIndex = 450;

    // ─── Tile layers ────────────────────────────────────────
    var tileLayerDefs = {
        light: L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
            { attribution: "&copy; CARTO &copy; OSM", subdomains: "abcd", maxZoom: 20 }
        ),
        physical: L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}",
            { attribution: "&copy; Esri", maxZoom: 8 }
        ),
        terrain: L.tileLayer(
            "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
            { attribution: "&copy; OpenTopoMap", maxZoom: 17 }
        ),
        standard: L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            { attribution: "&copy; OpenStreetMap", maxZoom: 19 }
        ),
        satellite: L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            { attribution: "&copy; Esri", maxZoom: 18 }
        ),
        dark: L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
            { attribution: "&copy; CARTO", subdomains: "abcd", maxZoom: 20 }
        ),
        blank: L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
            { attribution: "&copy; CARTO", subdomains: "abcd", maxZoom: 19 }
        ),
    };

    // Tile layer control labels
    var tileLayerLabels = {};
    tileLayerLabels[T["mapjs.layer_flat"] || "Light"] = tileLayerDefs.light;
    tileLayerLabels[T["mapjs.layer_physical"] || "Physical"] = tileLayerDefs.physical;
    tileLayerLabels[T["mapjs.layer_terrain"] || "Terrain"] = tileLayerDefs.terrain;
    tileLayerLabels[T["mapjs.layer_standard"] || "Standard"] = tileLayerDefs.standard;
    tileLayerLabels[T["mapjs.layer_satellite"] || "Satellite"] = tileLayerDefs.satellite;
    tileLayerLabels[T["mapjs.layer_dark"] || "Dark"] = tileLayerDefs.dark;

    var activeTile = null;
    var activeTileKey = "light";   // the tile the user/preset chose
    var PHYSICAL_MAX_ZOOM = 8;

    function setTileLayer(key) {
        activeTileKey = key;
        applyTileForZoom();
    }

    function applyTileForZoom() {
        var key = activeTileKey;
        // If physical is selected but zoom exceeds its max, fall back to blank
        if (key === "physical" && map.getZoom() > PHYSICAL_MAX_ZOOM) {
            key = "blank";
        }
        var desired = tileLayerDefs[key] || tileLayerDefs.light;
        if (activeTile === desired) return;
        if (activeTile) map.removeLayer(activeTile);
        activeTile = desired;
        activeTile.addTo(map);
    }

    setTileLayer("light");

    L.control.layers(tileLayerLabels, null, { position: "topright", collapsed: true }).addTo(map);

    // ─── Political layers ───────────────────────────────────
    var countriesData = {};
    var countryGeoLayer = null;
    var highlightedLayer = null;

    // City layer groups (6 tiers)
    var cityLayers = {
        capitals:   L.layerGroup(),
        mega:       L.layerGroup(),   // 5M+
        large:      L.layerGroup(),   // 1M–5M
        medium:     L.layerGroup(),   // 500K–1M
        small100k:  L.layerGroup(),   // 100K–500K
        tiny:       L.layerGroup(),   // <100K
    };

    // ── Tile-based city loading ─────────────────────────────
    var TILE_BASE = "/static/data/city_tiles/";
    var tileZoom = 7;           // matches build_city_tiles.py TILE_ZOOM
    var tileIndex = null;       // Set of available tile keys "x_y"
    var loadedTiles = {};       // "x_y" → true
    var loadingTiles = {};      // "x_y" → true
    var TILE_MIN_MAP_ZOOM = 7;  // start loading tiles at this map zoom

    // ─── Relief layers ──────────────────────────────────────
    var RELIEF_TYPE_COLORS = {
        volcano: "#DC143C", waterfall: "#00CED1", glacier: "#87CEEB",
        canyon: "#CD853F", strait: "#4682B4", cape: "#2E8B57",
        peninsula: "#3CB371", island: "#20B2AA", desert: "#DAA520",
        plateau: "#BC8F8F", plain: "#9ACD32", valley: "#228B22",
        mountain_range: "#A0522D", mountain: "#8B4513",
        lake: "#1E90FF", river: "#4169E1",
    };

    var RELIEF_TYPE_LABELS = {
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

    var ICON_BASE = "/static/img/icons/relief/";
    var GEOJSON_BASE = "/static/data/relief_geojson/";

    // Category groupings
    var RELIEF_CATS = {
        land:  ["mountain", "volcano", "mountain_range", "valley", "canyon", "desert", "plateau", "plain"],
        water: ["river", "lake", "waterfall", "glacier"],
        coast: ["strait", "cape", "peninsula", "island"],
    };

    var allReliefFeatures = [];
    var reliefCluster = null;
    var reliefGeoLayer = L.layerGroup();
    var geojsonCache = {};
    var geojsonLoading = {};
    var activeReliefTypes = new Set(Object.keys(RELIEF_TYPE_COLORS));
    var reliefVisible = false;

    // Relief legend control (added once, toggled)
    var reliefLegend = null;

    function reliefTypeLabel(type) {
        var labels = RELIEF_TYPE_LABELS[type];
        return labels ? (labels[LANG] || labels.en || type) : type.replace(/_/g, " ");
    }

    // ─── Helpers ────────────────────────────────────────────
    function formatNumber(n) {
        if (n === "" || n === null || n === undefined) return "—";
        var num = Number(n);
        if (isNaN(num)) return n;
        if (num >= 1e12) return (num / 1e12).toFixed(2) + " T";
        if (num >= 1e9) return (num / 1e9).toFixed(2) + " B";
        if (num >= 1e6) return (num / 1e6).toFixed(2) + " M";
        if (num >= 1e3) return num.toLocaleString(LANG === "en" ? "en-US" : "es-ES");
        return String(num);
    }

    function formatPop(n) {
        if (!n || n <= 0) return "";
        var u = T["mapjs.inhabitants"] || "inhab.";
        if (n >= 1e6) return (n / 1e6).toFixed(1) + "M " + u;
        if (n >= 1e3) return Math.round(n / 1e3) + "K " + u;
        return n + " " + u;
    }

    function flagUrl(iso3) { return "/static/data/images/flags/" + iso3 + ".svg"; }
    function flagUrlFallback(iso3) { return "/static/data/images/flags/" + iso3 + ".png"; }

    // ─── Country GeoJSON styling ────────────────────────────
    function defaultStyle() {
        return { fillColor: "#1a73e8", fillOpacity: 0.12, color: "#1a73e8", weight: 1.2, opacity: 0.6 };
    }
    function highlightStyle() {
        return { fillColor: "#1a73e8", fillOpacity: 0.35, color: "#0d47a1", weight: 2.5, opacity: 1 };
    }

    function getIso3(feature) {
        var p = feature.properties || {};
        return p.ISO_A3 || p.iso_a3 || p.ADM0_A3 || p.adm0_a3 || "";
    }
    function getCountryName(feature) {
        var p = feature.properties || {};
        return p.ADMIN || p.admin || p.name || p.NAME || p.GEOUNIT || "";
    }

    function onEachCountryFeature(feature, layer) {
        var iso3 = getIso3(feature);
        var name = getCountryName(feature);
        var country = countriesData[iso3] || {};
        var capital = country.capital || "";

        layer.bindTooltip(
            '<div class="country-tooltip">' +
            '<div class="tooltip-name">' + (country.name || name) + '</div>' +
            (capital ? '<div class="tooltip-capital">🏛️ ' + capital + '</div>' : '') +
            '</div>',
            { sticky: true, className: "country-tooltip-wrapper", direction: "top", offset: [0, -10] }
        );

        layer.on("mouseover", function () {
            if (highlightedLayer !== layer) { layer.setStyle(highlightStyle()); layer.bringToFront(); }
        });
        layer.on("mouseout", function () {
            if (highlightedLayer !== layer) countryGeoLayer.resetStyle(layer);
        });
        layer.on("click", function () {
            if (highlightedLayer && highlightedLayer !== layer) countryGeoLayer.resetStyle(highlightedLayer);
            highlightedLayer = layer;
            layer.setStyle(highlightStyle());
            showCountryModal(iso3, name);
        });
    }

    // ─── Country modal ──────────────────────────────────────
    var modalOverlay = document.getElementById("modal-overlay");
    var modalClose = document.getElementById("modal-close");

    function closeModal() {
        modalOverlay.classList.remove("active");
        if (highlightedLayer) {
            if (countryGeoLayer) countryGeoLayer.resetStyle(highlightedLayer);
            highlightedLayer = null;
        }
    }
    modalClose.addEventListener("click", closeModal);
    modalOverlay.addEventListener("click", function (e) { if (e.target === modalOverlay) closeModal(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeModal(); });

    function showCountryModal(iso3, fallbackName) {
        var c = countriesData[iso3] || {};
        var name = c.name || fallbackName;

        var flagImg = document.getElementById("modal-flag");
        flagImg.src = flagUrl(iso3);
        flagImg.onerror = function () {
            this.src = flagUrlFallback(iso3);
            this.onerror = function () { this.src = ""; this.style.display = "none"; };
        };
        flagImg.style.display = "";

        document.getElementById("modal-name").textContent = name;
        document.getElementById("modal-official").textContent = c.name_official || "";
        document.getElementById("modal-body").innerHTML = buildModalContent(c);
        modalOverlay.classList.add("active");
    }

    function buildModalContent(c) {
        function item(label, value) {
            if (value === "" || value === undefined || value === null || value === "[]") return "";
            return '<div class="modal-item"><span class="modal-item-label">' + label +
                '</span><span class="modal-item-value">' + value + '</span></div>';
        }

        var languages = "";
        try {
            var langs = typeof c.official_languages === "string" ? JSON.parse(c.official_languages) : c.official_languages;
            if (Array.isArray(langs)) languages = langs.join(", ");
        } catch (e) { languages = c.official_languages || ""; }

        var citiesHtml = "";
        try {
            var topCities = typeof c.top_cities === "string" ? JSON.parse(c.top_cities) : c.top_cities;
            if (Array.isArray(topCities) && topCities.length > 0) {
                citiesHtml = '<div class="modal-section"><div class="modal-section-title">' +
                    (T["mapjs.top_cities"] || "🏙️ Top cities") + '</div><div class="modal-grid">';
                topCities.forEach(function (city) {
                    var badge = city.is_capital ? ' <span style="color:var(--blue-500);font-size:0.75rem;">⭐</span>' : "";
                    citiesHtml += item(city.name + badge, formatNumber(city.population) + " " + (T["mapjs.inhabitants"] || "inhab."));
                });
                citiesHtml += '</div></div>';
            }
        } catch (e) { /* ignore */ }

        var _t = function (k) { return T[k] || k; };

        return '<div class="modal-section"><div class="modal-section-title">' + _t("mapjs.section_general") + '</div><div class="modal-grid">' +
            item(_t("mapjs.capital"), c.capital) +
            item(_t("mapjs.region"), c.region) +
            item(_t("mapjs.subregion"), c.subregion) +
            item(_t("mapjs.continent"), c.continent) +
            item(_t("mapjs.lat_lon"), c.lat && c.lon ? Number(c.lat).toFixed(2) + "° / " + Number(c.lon).toFixed(2) + "°" : "") +
            item(_t("mapjs.timezone"), c.timezones) +
            item("ISO", c.iso_a2 + " / " + c.iso_a3) +
            item(_t("mapjs.domain"), c.tld) +
            '</div></div>' +
            '<div class="modal-section"><div class="modal-section-title">' + _t("mapjs.section_population") + '</div><div class="modal-grid">' +
            item(_t("mapjs.population"), formatNumber(c.population)) +
            item(_t("mapjs.area"), c.area_km2 ? formatNumber(c.area_km2) + " km²" : "") +
            item(_t("mapjs.density"), c.density_per_km2 ? Number(c.density_per_km2).toFixed(1) + " hab/km²" : "") +
            item(_t("mapjs.birth_rate"), c.birth_rate ? Number(c.birth_rate).toFixed(1) + " ‰" : "") +
            item(_t("mapjs.immigrant_pct"), c.immigrant_pct ? Number(c.immigrant_pct).toFixed(1) + "%" : "") +
            item(_t("mapjs.life_expectancy"), c.life_expectancy ? Number(c.life_expectancy).toFixed(1) + (LANG === "en" ? " years" : " años") : "") +
            item(_t("mapjs.urban_pop"), c.urban_population_pct ? Number(c.urban_population_pct).toFixed(1) + "%" : "") +
            item(_t("mapjs.literacy"), c.literacy_rate ? Number(c.literacy_rate).toFixed(1) + "%" : "") +
            '</div></div>' +
            citiesHtml +
            '<div class="modal-section"><div class="modal-section-title">' + _t("mapjs.section_economy") + '</div><div class="modal-grid">' +
            item(_t("mapjs.gdp"), c.gdp_usd ? "$" + formatNumber(c.gdp_usd) : "") +
            item(_t("mapjs.gdp_per_capita"), c.gdp_per_capita_usd ? "$" + formatNumber(c.gdp_per_capita_usd) : "") +
            item(_t("mapjs.gini"), c.gini || "") +
            item(_t("mapjs.hdi"), c.hdi || "") +
            item(_t("mapjs.currency"), c.currency_name ? c.currency_name + " (" + c.currency_code + ")" : "") +
            '</div></div>' +
            '<div class="modal-section"><div class="modal-section-title">' + _t("mapjs.section_languages") + '</div><div class="modal-grid">' +
            item(_t("mapjs.main_language"), c.main_language) +
            item(_t("mapjs.secondary_language"), c.secondary_language) +
            item(_t("mapjs.official_languages"), languages) +
            item(_t("mapjs.car_side"), c.car_side) +
            item(_t("mapjs.start_of_week"), c.start_of_week) +
            '</div></div>' +
            '<div class="modal-section"><div class="modal-section-title">' + _t("mapjs.section_links") + '</div><div class="modal-grid">' +
            (c.google_maps ? '<div class="modal-item"><a href="' + c.google_maps + '" target="_blank" rel="noopener" style="color:var(--blue-500);">' + _t("mapjs.google_maps") + '</a></div>' : "") +
            (c.osm_maps ? '<div class="modal-item"><a href="' + c.osm_maps + '" target="_blank" rel="noopener" style="color:var(--blue-500);">' + _t("mapjs.osm") + '</a></div>' : "") +
            '</div></div>';
    }

    // ─── City markers ───────────────────────────────────────

    // Style config for L.circleMarker (non-capital cities)
    var CITY_CIRCLE_STYLES = {
        mega:    { radius: 7,   color: "#fff", weight: 2,   fillColor: "#1a1a1a", fillOpacity: 1 },
        large:   { radius: 6.5, color: "#fff", weight: 1.5, fillColor: "#333",    fillOpacity: 1 },
        medium:  { radius: 5.5, color: "#fff", weight: 1.5, fillColor: "#555",    fillOpacity: 1 },
        small:   { radius: 4.5, color: "#fff", weight: 1,   fillColor: "#777",    fillOpacity: 1 },
        tiny:    { radius: 4,   color: "#fff", weight: 0.8, fillColor: "#aaa",    fillOpacity: 1 },
    };

    // Capital star icon via L.divIcon with inline SVG
    var starSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="SIZE" height="SIZE">' +
        '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14l-5-4.87 6.91-1.01L12 2z" ' +
        'fill="#222" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';

    function makeCapitalIcon(pop) {
        var size = pop >= 5000000 ? 22 : pop >= 1000000 ? 18 : 14;
        var svg = starSvg.replace(/SIZE/g, size);
        return L.divIcon({
            className: "capital-star-icon",
            html: svg,
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
            popupAnchor: [0, -size / 2],
        });
    }

    function getCityCircleStyle(pop) {
        if (pop >= 5000000) return CITY_CIRCLE_STYLES.mega;
        if (pop >= 1000000) return CITY_CIRCLE_STYLES.large;
        if (pop >= 500000)  return CITY_CIRCLE_STYLES.medium;
        if (pop >= 100000)  return CITY_CIRCLE_STYLES.small;
        return CITY_CIRCLE_STYLES.tiny;
    }

    function cityTooltipHtml(city) {
        return '<div class="city-tooltip-content">' +
            '<div class="ct-name">' + city.name +
            (city.is_capital ? '<span class="ct-badge">' + (T["mapjs.capital_badge"] || "CAPITAL") + '</span>' : "") +
            '</div>' +
            '<div class="ct-country">' + city.country + '</div>' +
            (city.population > 0 ? '<div class="ct-pop">' + formatPop(city.population) + '</div>' : "") +
            '</div>';
    }

    function cityPopupHtml(city) {
        var langKey = "name_" + LANG;
        var displayName = city[langKey] || city.name;
        var html = '<div class="city-popup">';
        html += '<div class="cp-name">' + displayName;
        if (city.is_capital) html += ' <span class="cp-badge">★ ' + (T["mapjs.capital_badge"] || "CAPITAL") + '</span>';
        html += '</div>';
        html += '<div class="cp-country">' + city.country + '</div>';
        if (city.admin1_name) html += '<div class="cp-detail">' + city.admin1_name + '</div>';
        if (city.population > 0) html += '<div class="cp-stat">👥 ' + formatPop(city.population) + '</div>';
        if (city.metro_population) html += '<div class="cp-stat">🏙️ ' + formatPop(city.metro_population) + ' (metro)</div>';
        if (city.elevation) html += '<div class="cp-stat">⛰️ ' + Math.round(city.elevation).toLocaleString() + ' m</div>';
        if (city.annual_mean_temp) html += '<div class="cp-stat">🌡️ ' + city.annual_mean_temp.toFixed(1) + ' °C</div>';
        if (city.annual_precipitation) html += '<div class="cp-stat">🌧️ ' + Math.round(city.annual_precipitation) + ' mm</div>';
        if (city.sunshine_hours_yr) html += '<div class="cp-stat">☀️ ' + Math.round(city.sunshine_hours_yr).toLocaleString() + ' h</div>';
        if (city.timezone) html += '<div class="cp-detail cp-tz">' + city.timezone + '</div>';
        html += '</div>';
        return html;
    }

    function addCityMarkers(cities) {
        cities.forEach(function (city) {
            if (!city.lat || !city.lon) return;
            var pop = city.population || 0;
            var isCapital = city.is_capital;
            var marker;

            if (isCapital) {
                marker = L.marker([city.lat, city.lon], {
                    icon: makeCapitalIcon(pop),
                    zIndexOffset: 1000,
                });
            } else {
                var style = getCityCircleStyle(pop);
                marker = L.circleMarker([city.lat, city.lon], {
                    pane: "cityPane",
                    radius: style.radius,
                    color: style.color,
                    weight: style.weight,
                    fillColor: style.fillColor,
                    fillOpacity: style.fillOpacity,
                });
            }

            marker.bindTooltip(cityTooltipHtml(city), {
                direction: "top", offset: [0, -8], className: "country-tooltip-wrapper",
            });
            marker.bindPopup(cityPopupHtml(city), { maxWidth: 260 });

            if (isCapital)          cityLayers.capitals.addLayer(marker);
            else if (pop >= 5000000) cityLayers.mega.addLayer(marker);
            else if (pop >= 1000000) cityLayers.large.addLayer(marker);
            else if (pop >= 500000)  cityLayers.medium.addLayer(marker);
            else if (pop >= 100000)  cityLayers.small100k.addLayer(marker);
            else                     cityLayers.tiny.addLayer(marker);
        });
    }

    // ─── Tile-based city loading ─────────────────────────────
    function latLonToTile(lat, lon, zoom) {
        var n = Math.pow(2, zoom);
        var x = Math.floor((lon + 180) / 360 * n);
        var latRad = Math.max(-85, Math.min(85, lat)) * Math.PI / 180;
        var y = Math.floor((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n);
        return [Math.max(0, Math.min(n - 1, x)), Math.max(0, Math.min(n - 1, y))];
    }

    function getVisibleTileKeys() {
        var bounds = map.getBounds();
        var sw = bounds.getSouthWest();
        var ne = bounds.getNorthEast();
        var swTile = latLonToTile(sw.lat, sw.lng, tileZoom);
        var neTile = latLonToTile(ne.lat, ne.lng, tileZoom);
        var n = Math.pow(2, tileZoom);
        var keys = [];
        // tile y increases downward: neTile[1] <= swTile[1]
        for (var y = neTile[1]; y <= swTile[1]; y++) {
            if (sw.lng <= ne.lng) {
                for (var x = swTile[0]; x <= neTile[0]; x++) {
                    keys.push(x + "_" + y);
                }
            } else {
                // date-line crossing
                for (var x = swTile[0]; x < n; x++) keys.push(x + "_" + y);
                for (var x = 0; x <= neTile[0]; x++) keys.push(x + "_" + y);
            }
        }
        return keys;
    }

    function loadCityTile(key) {
        if (loadedTiles[key] || loadingTiles[key]) return;
        if (tileIndex && !tileIndex.has(key)) return;
        loadingTiles[key] = true;
        fetch(TILE_BASE + key + ".json")
            .then(function (r) { return r.ok ? r.json() : []; })
            .then(function (cities) {
                addCityMarkers(cities);
                loadedTiles[key] = true;
                delete loadingTiles[key];
                updateCityVisibility();
                console.log("[GeoFreak] Tile " + key + " loaded:", cities.length, "cities");
            })
            .catch(function (err) {
                delete loadingTiles[key];
                console.error("[GeoFreak] Tile " + key + " error:", err);
            });
    }

    function checkAndLoadTiles() {
        var zoom = map.getZoom();
        if (zoom < TILE_MIN_MAP_ZOOM) return;
        if (!tileIndex) {
            console.warn("[GeoFreak] checkAndLoadTiles: no tileIndex");
            return;
        }
        var keys = getVisibleTileKeys();
        var newKeys = keys.filter(function (k) { return !loadedTiles[k] && !loadingTiles[k] && tileIndex.has(k); });
        if (newKeys.length > 0) {
            console.log("[GeoFreak] Loading", newKeys.length, "tiles at zoom", zoom);
        }
        for (var i = 0; i < keys.length; i++) {
            loadCityTile(keys[i]);
        }
    }

    // ─── Relief marker/GeoJSON creation ─────────────────────
    function createReliefSvgIcon(type) {
        return L.divIcon({
            className: "relief-svg-icon",
            html: '<img src="' + ICON_BASE + type + '.svg" width="20" height="20" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,0.3))">',
            iconSize: [20, 20], iconAnchor: [10, 10], popupAnchor: [0, -12],
        });
    }

    function reliefPopupHtml(f) {
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        var tl = reliefTypeLabel(f.type);
        var html = '<div class="relief-popup"><div class="rp-name">' + displayName + '</div><div class="rp-type">' + tl + '</div>';
        if (f.country_names_en) html += '<div class="rp-country">' + f.country_names_en + '</div>';
        if (f.elevation_m != null) html += '<div class="rp-stat">' + f.elevation_m.toLocaleString() + ' m</div>';
        if (f.length_km != null) html += '<div class="rp-stat">' + f.length_km.toLocaleString() + ' km</div>';
        if (f.area_km2 != null) html += '<div class="rp-stat">' + f.area_km2.toLocaleString() + ' km\u00B2</div>';
        html += '</div>';
        return html;
    }

    function createReliefIconMarker(f) {
        var icon = createReliefSvgIcon(f.type);
        var marker = L.marker([f.lat, f.lon], { icon: icon });
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        marker.bindPopup(reliefPopupHtml(f));
        marker.bindTooltip(displayName, { direction: "top", offset: [0, -12], className: "country-tooltip-wrapper" });
        marker._featureData = f;
        wireReliefMarkerForEdit(marker);
        return marker;
    }

    function createReliefGeoJsonLayer(f, geojson) {
        var color = RELIEF_TYPE_COLORS[f.type] || "#999";
        var isLine = (geojson.type === "LineString" || geojson.type === "MultiLineString");
        var isRiver = (f.type === "river");
        var baseStyle;

        if (isRiver) {
            baseStyle = { color: color, weight: 4, opacity: 0.55, lineCap: "round", lineJoin: "round", fillOpacity: 0 };
        } else if (isLine) {
            baseStyle = { color: color, weight: 3, opacity: 0.8, lineCap: "round", lineJoin: "round", fillOpacity: 0 };
        } else {
            baseStyle = { color: color, weight: 2.5, opacity: 0.8, fillColor: color, fillOpacity: 0.2 };
        }

        var layer = L.geoJSON(geojson, { style: baseStyle });
        var langKey = "name_" + LANG;
        var displayName = f[langKey] || f.name_en || f.name;
        layer.bindPopup(reliefPopupHtml(f));
        layer.bindTooltip(displayName, { sticky: true, className: "country-tooltip-wrapper" });
        layer._featureData = f;
        wireReliefGeoLayerForEdit(layer);

        layer.eachLayer(function (sub) {
            sub.on("mouseover", function () {
                sub.setStyle({ weight: isRiver ? 6 : (isLine ? 4.5 : 4), opacity: 1, fillOpacity: isLine ? 0 : 0.35 });
            });
            sub.on("mouseout", function () { sub.setStyle(baseStyle); });
        });

        return layer;
    }

    // ─── Relief filtering & rebuild ─────────────────────────
    function getFilteredRelief() {
        var result = [];
        for (var i = 0; i < allReliefFeatures.length; i++) {
            var f = allReliefFeatures[i];
            if (activeReliefTypes.has(f.type)) result.push(f);
        }
        return result;
    }

    function rebuildReliefMarkers() {
        if (!reliefCluster) return;
        reliefCluster.clearLayers();
        reliefGeoLayer.clearLayers();
        if (!reliefVisible) return;

        var filtered = getFilteredRelief();
        for (var i = 0; i < filtered.length; i++) {
            reliefCluster.addLayer(createReliefIconMarker(filtered[i]));
        }
        showReliefGeoJsonInView();
    }

    function showReliefGeoJsonInView() {
        reliefGeoLayer.clearLayers();
        if (!reliefVisible) return;

        var currentZoom = map.getZoom();
        var bounds = map.getBounds();
        var filtered = getFilteredRelief();
        var toFetch = [];

        for (var i = 0; i < filtered.length; i++) {
            var f = filtered[i];
            if (!f.has_geojson) continue;
            if (currentZoom < f.min_zoom) continue;
            if (!bounds.contains([f.lat, f.lon])) continue;

            var cached = geojsonCache[f.wikidata_id];
            if (cached) {
                reliefGeoLayer.addLayer(createReliefGeoJsonLayer(f, cached));
            } else if (!geojsonLoading[f.wikidata_id]) {
                toFetch.push(f);
            }
        }
        if (toFetch.length > 0) fetchReliefGeoJsonBatch(toFetch);
    }

    function fetchReliefGeoJsonBatch(features) {
        var batchSize = 20;
        var batch = features.slice(0, batchSize);
        batch.forEach(function (f) { geojsonLoading[f.wikidata_id] = true; });

        Promise.all(batch.map(function (f) {
            return fetch(GEOJSON_BASE + f.wikidata_id + ".geojson")
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) {
                    delete geojsonLoading[f.wikidata_id];
                    if (data && data.geometry) geojsonCache[f.wikidata_id] = data.geometry;
                })
                .catch(function () { delete geojsonLoading[f.wikidata_id]; });
        })).then(function () {
            showReliefGeoJsonInView();
            var remaining = features.slice(batchSize);
            if (remaining.length > 0) fetchReliefGeoJsonBatch(remaining);
        });
    }

    // Relief legend
    function addReliefLegend() {
        if (reliefLegend) return;
        var types = Object.keys(RELIEF_TYPE_COLORS);
        reliefLegend = L.control({ position: "bottomleft" });
        reliefLegend.onAdd = function () {
            var div = L.DomUtil.create("div", "relief-legend");
            types.forEach(function (t) {
                div.innerHTML += '<div class="relief-legend-item">' +
                    '<img src="' + ICON_BASE + t + '.svg" class="relief-legend-icon" width="14" height="14">' +
                    '<span>' + reliefTypeLabel(t) + '</span></div>';
            });
            L.DomEvent.disableClickPropagation(div);
            return div;
        };
        reliefLegend.addTo(map);
    }

    function toggleReliefLegend(show) {
        if (!reliefLegend) { if (show) addReliefLegend(); return; }
        var el = reliefLegend.getContainer();
        if (el) el.style.display = show ? "" : "none";
    }

    // ─── Zoom-based city layer visibility ───────────────────
    var cityMinZoom = {
        capitals: 3, mega: 2, large: 3, medium: 4, small100k: 7, tiny: 9,
    };

    function updateCityVisibility() {
        var zoom = map.getZoom();
        Object.keys(cityLayers).forEach(function (key) {
            var layer = cityLayers[key];
            var minZ = cityMinZoom[key];
            if (!layerState[key]) {
                if (map.hasLayer(layer)) map.removeLayer(layer);
                return;
            }
            if (zoom >= minZ) {
                if (!map.hasLayer(layer)) map.addLayer(layer);
            } else {
                if (map.hasLayer(layer)) map.removeLayer(layer);
            }
        });
    }

    // ─── Auto-hide country borders at high zoom ─────────────
    var countryBordersAutoHidden = false;
    var COUNTRY_AUTOHIDE_MIN_ZOOM = 7;

    function updateCountryBordersForZoom() {
        if (!countryGeoLayer || !layerState.countries) return;
        var zoom = map.getZoom();

        if (zoom < COUNTRY_AUTOHIDE_MIN_ZOOM) {
            // At low zoom, always show borders
            if (countryBordersAutoHidden) {
                map.addLayer(countryGeoLayer);
                countryBordersAutoHidden = false;
            }
            return;
        }

        // Check if entire viewport fits within any single country's bounding box
        var viewBounds = map.getBounds();
        var insideSingle = false;
        countryGeoLayer.eachLayer(function (layer) {
            if (insideSingle) return;
            try {
                if (layer.getBounds().contains(viewBounds)) insideSingle = true;
            } catch (e) { /* skip layers without bounds */ }
        });

        if (insideSingle && !countryBordersAutoHidden) {
            map.removeLayer(countryGeoLayer);
            countryBordersAutoHidden = true;
        } else if (!insideSingle && countryBordersAutoHidden) {
            map.addLayer(countryGeoLayer);
            countryBordersAutoHidden = false;
        }
    }

    // ─── Preset system ──────────────────────────────────────
    var presetButtons = document.querySelectorAll(".map-preset");
    var currentPreset = "political";

    // Layer state tracks which logical layers are enabled
    // Visibility is controlled by cityMinZoom per layer, so enable all here
    var layerState = {
        countries: true, capitals: true, mega: true, large: true,
        medium: true, small100k: true, tiny: true,
        reliefAll: false, reliefLand: false, reliefWater: false, reliefCoast: false,
    };

    var customState = JSON.parse(JSON.stringify(layerState));

    var presets = {
        political: {
            tile: "light", countries: true, capitals: true, mega: true,
            large: true, medium: true, small100k: true, tiny: true,
            reliefAll: false, reliefLand: false, reliefWater: false, reliefCoast: false,
        },
        physical: {
            tile: "physical", countries: false, capitals: false, mega: false,
            large: false, medium: false, small100k: false, tiny: false,
            reliefAll: true, reliefLand: false, reliefWater: false, reliefCoast: false,
        },
    };

    // ─── Layers control (Leaflet, topright) ─────────────────
    var _t = function (k) { return T[k] || k; };
    var layersControl = null;
    var layersExpanded = false;

    var LAYERS_CHECKBOX_MAP = {
        countries: "countries", capitals: "capitals",
        cities5m: "mega", cities1m: "large", cities500k: "medium",
        cities100k: "small100k", citiesOther: "tiny",
        reliefAll: "reliefAll", reliefLand: "reliefLand",
        reliefWater: "reliefWater", reliefCoast: "reliefCoast",
    };

    function buildLayersControl() {
        var LayersControl = L.Control.extend({
            options: { position: "topright" },
            onAdd: function () {
                var container = L.DomUtil.create("div", "map-layers-control leaflet-bar");
                L.DomEvent.disableClickPropagation(container);
                L.DomEvent.disableScrollPropagation(container);

                // Toggle button
                var toggle = L.DomUtil.create("a", "map-layers-toggle", container);
                toggle.href = "#";
                toggle.title = _t("mapjs.preset_custom");
                toggle.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18"><path d="M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z" fill="currentColor"/></svg>';
                toggle.onclick = function (e) {
                    e.preventDefault();
                    layersExpanded = !layersExpanded;
                    body.style.display = layersExpanded ? "block" : "none";
                };

                // Body
                var body = L.DomUtil.create("div", "map-layers-body", container);
                body.style.display = "none";

                // Political section
                body.innerHTML += '<div class="mlc-section">' + _t("mapjs.section_custom_political") + '</div>';
                var polItems = [
                    ["countries",   _t("mapjs.layer_countries")],
                    ["capitals",    _t("mapjs.layer_capitals")],
                    ["cities5m",    _t("mapjs.layer_cities_5m")],
                    ["cities1m",    _t("mapjs.layer_cities_1m")],
                    ["cities500k",  _t("mapjs.layer_cities_500k")],
                    ["cities100k",  _t("mapjs.layer_cities_100k")],
                    ["citiesOther", _t("mapjs.layer_cities_other")],
                ];
                polItems.forEach(function (item) {
                    var lbl = L.DomUtil.create("label", "mlc-label", body);
                    lbl.innerHTML = '<input type="checkbox" data-layer="' + item[0] + '"> ' + item[1];
                });

                // Relief section
                body.innerHTML += '<div class="mlc-section">' + _t("mapjs.section_custom_relief") + '</div>';
                var relItems = [
                    ["reliefAll",   _t("mapjs.layer_relief_all")],
                    ["reliefLand",  _t("mapjs.layer_relief_land")],
                    ["reliefWater", _t("mapjs.layer_relief_water")],
                    ["reliefCoast", _t("mapjs.layer_relief_coast")],
                ];
                relItems.forEach(function (item) {
                    var lbl = L.DomUtil.create("label", "mlc-label", body);
                    lbl.innerHTML = '<input type="checkbox" data-layer="' + item[0] + '"> ' + item[1];
                });

                // Wire up checkboxes
                body.querySelectorAll("input[type=checkbox]").forEach(function (cb) {
                    cb.addEventListener("change", onLayerCheckboxChange);
                });

                container._body = body;
                return container;
            },
        });
        layersControl = new LayersControl();
        layersControl.addTo(map);
    }

    function onLayerCheckboxChange(e) {
        var cb = e.target;
        var layerKey = LAYERS_CHECKBOX_MAP[cb.dataset.layer];
        if (layerKey === undefined) return;

        // Auto-switch to custom preset
        if (currentPreset !== "custom") {
            currentPreset = "custom";
            presetButtons.forEach(function (b) {
                b.classList.toggle("active", b.dataset.preset === "custom");
            });
        }

        layerState[layerKey] = cb.checked;
        customState[layerKey] = cb.checked;

        // Mutual exclusion for relief
        if (cb.dataset.layer === "reliefAll" && cb.checked) {
            layerState.reliefLand = false; layerState.reliefWater = false; layerState.reliefCoast = false;
            customState.reliefLand = false; customState.reliefWater = false; customState.reliefCoast = false;
            syncLayersCheckboxes();
        } else if (["reliefLand", "reliefWater", "reliefCoast"].indexOf(layerKey) >= 0 && cb.checked) {
            layerState.reliefAll = false; customState.reliefAll = false;
            syncLayersCheckboxes();
        }

        // Apply
        if (layerKey === "countries") {
            if (countryGeoLayer) { cb.checked ? map.addLayer(countryGeoLayer) : map.removeLayer(countryGeoLayer); }
        } else if (["capitals", "mega", "large", "medium", "small100k", "tiny"].indexOf(layerKey) >= 0) {
            updateCityVisibility();
        } else {
            updateReliefFromState();
        }
    }

    function syncLayersCheckboxes() {
        if (!layersControl) return;
        var container = layersControl.getContainer();
        if (!container) return;
        container.querySelectorAll("input[type=checkbox]").forEach(function (cb) {
            var layerKey = LAYERS_CHECKBOX_MAP[cb.dataset.layer];
            if (layerKey !== undefined) cb.checked = layerState[layerKey];
        });
    }

    function expandLayersControl(expand) {
        if (!layersControl) return;
        var container = layersControl.getContainer();
        if (!container) return;
        layersExpanded = expand;
        container._body.style.display = expand ? "block" : "none";
    }

    function updateReliefFromState() {
        var anyRelief = layerState.reliefAll || layerState.reliefLand || layerState.reliefWater || layerState.reliefCoast;
        reliefVisible = anyRelief;

        if (anyRelief) {
            activeReliefTypes = new Set();
            if (layerState.reliefAll) {
                Object.keys(RELIEF_TYPE_COLORS).forEach(function (t) { activeReliefTypes.add(t); });
            } else {
                if (layerState.reliefLand) RELIEF_CATS.land.forEach(function (t) { activeReliefTypes.add(t); });
                if (layerState.reliefWater) RELIEF_CATS.water.forEach(function (t) { activeReliefTypes.add(t); });
                if (layerState.reliefCoast) RELIEF_CATS.coast.forEach(function (t) { activeReliefTypes.add(t); });
            }
            if (!map.hasLayer(reliefCluster)) map.addLayer(reliefCluster);
            if (!map.hasLayer(reliefGeoLayer)) map.addLayer(reliefGeoLayer);
        } else {
            activeReliefTypes.clear();
            if (map.hasLayer(reliefCluster)) map.removeLayer(reliefCluster);
            if (map.hasLayer(reliefGeoLayer)) map.removeLayer(reliefGeoLayer);
        }

        rebuildReliefMarkers();
        toggleReliefLegend(anyRelief);
    }

    function applyPreset(name) {
        currentPreset = name;
        var p = name === "custom" ? customState : presets[name];

        if (p.tile) setTileLayer(p.tile);

        layerState.countries = p.countries;
        countryBordersAutoHidden = false;  // reset auto-hide on preset change
        if (countryGeoLayer) {
            if (p.countries && !map.hasLayer(countryGeoLayer)) map.addLayer(countryGeoLayer);
            else if (!p.countries && map.hasLayer(countryGeoLayer)) map.removeLayer(countryGeoLayer);
        }
        if (p.countries) updateCountryBordersForZoom();

        ["capitals", "mega", "large", "medium", "small100k", "tiny"].forEach(function (k) {
            layerState[k] = p[k];
        });
        updateCityVisibility();

        layerState.reliefAll = p.reliefAll;
        layerState.reliefLand = p.reliefLand;
        layerState.reliefWater = p.reliefWater;
        layerState.reliefCoast = p.reliefCoast;
        updateReliefFromState();

        presetButtons.forEach(function (btn) {
            btn.classList.toggle("active", btn.dataset.preset === name);
        });

        syncLayersCheckboxes();

        if (name === "custom") expandLayersControl(true);
    }

    // Preset button click handlers
    presetButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var preset = btn.dataset.preset;
            if (preset === "custom" && currentPreset === "custom") {
                expandLayersControl(!layersExpanded);
                return;
            }
            applyPreset(preset);
        });
    });

    // ─── Edit mode ──────────────────────────────────────────
    var editMode = false;
    var editSelectedType = null;
    var editPendingMarker = null;
    var editDrawing = { active: false, points: [], previewLine: null, rubberBand: null, vertices: [] };
    var editFormContext = null; // {type, geojson, marker, latlng, existing: null|featureData}

    // ── Editing existing features ──
    var editSelected = null;        // { feature, marker, geoLayer, editVertices[], originalLatLng, originalGeojson }

    // Edit toggle control (Leaflet topleft)
    var editControl = null;
    function buildEditControl() {
        var EditControl = L.Control.extend({
            options: { position: "topleft" },
            onAdd: function () {
                var btn = L.DomUtil.create("div", "map-edit-btn leaflet-bar");
                btn.innerHTML = '<a href="#" title="' + (_t("mapjs.edit_mode") || "Edit") + '">✏️</a>';
                L.DomEvent.disableClickPropagation(btn);
                btn.querySelector("a").onclick = function (e) {
                    e.preventDefault();
                    toggleEditMode();
                };
                return btn;
            },
        });
        editControl = new EditControl();
        editControl.addTo(map);
    }

    // Edit panel (type selector)
    var editPanel = null;
    function buildEditPanel() {
        var panel = document.createElement("div");
        panel.className = "map-edit-panel";
        panel.style.display = "none";
        panel.id = "edit-panel";

        var html = '<div class="mep-header">' + (_t("mapjs.edit_select_type") || "Select type") + '</div>';
        var cats = [
            { key: "land",  label: _t("mapjs.edit_cat_land") || "Land",  types: RELIEF_CATS.land },
            { key: "water", label: _t("mapjs.edit_cat_water") || "Water", types: RELIEF_CATS.water },
            { key: "coast", label: _t("mapjs.edit_cat_coast") || "Coast", types: RELIEF_CATS.coast },
        ];

        cats.forEach(function (cat) {
            html += '<div class="mep-cat">' + cat.label + '</div>';
            cat.types.forEach(function (t) {
                html += '<div class="mep-type" data-type="' + t + '">' +
                    '<img src="' + ICON_BASE + t + '.svg" width="18" height="18">' +
                    '<span>' + reliefTypeLabel(t) + '</span></div>';
            });
        });
        html += '<div class="mep-instructions" id="edit-instructions"></div>';
        html += '<div class="mep-actions">';
        html += '<button class="edit-btn edit-btn-cancel mep-btn-cancel" id="edit-cancel-draw">' + (_t("mapjs.edit_cancel") || "Cancel") + '</button>';
        html += '<button class="edit-btn edit-btn-submit mep-btn-save" id="edit-save-btn" style="display:none">' + (_t("mapjs.edit_save") || "Save") + '</button>';
        html += '</div>';

        panel.innerHTML = html;
        document.querySelector(".map-page").appendChild(panel);
        editPanel = panel;

        // Type selection handlers
        panel.querySelectorAll(".mep-type").forEach(function (el) {
            el.addEventListener("click", function () {
                selectEditType(el.dataset.type);
            });
        });

        // Cancel button exits edit mode entirely
        document.getElementById("edit-cancel-draw").addEventListener("click", function () {
            toggleEditMode();
        });

        // Save button
        document.getElementById("edit-save-btn").addEventListener("click", function () {
            openEditForm();
        });
    }

    function toggleEditMode() {
        editMode = !editMode;
        var btn = editControl.getContainer().querySelector("a");
        if (editMode) {
            btn.classList.add("active");
            editPanel.style.display = "block";
            document.getElementById("map").classList.add("editing");
        } else {
            btn.classList.remove("active");
            editPanel.style.display = "none";
            document.getElementById("map").classList.remove("editing");
            cancelEditDrawing();
            clearEditSelection();
            deselectExistingFeature();
        }
    }

    function selectEditType(type) {
        editSelectedType = type;
        editPanel.querySelectorAll(".mep-type").forEach(function (el) {
            el.classList.toggle("selected", el.dataset.type === type);
        });
        cancelEditDrawing();
        deselectExistingFeature();
        var instrEl = document.getElementById("edit-instructions");
        var isLine = (type === "river");
        instrEl.textContent = isLine
            ? (_t("mapjs.edit_draw_line") || "Click on map to draw line. Double-click to finish.")
            : (_t("mapjs.edit_place_point") || "Click on map to place or draw. Double-click to close polygon.");
    }

    function clearEditSelection() {
        editSelectedType = null;
        if (editPanel) {
            editPanel.querySelectorAll(".mep-type").forEach(function (el) { el.classList.remove("selected"); });
            document.getElementById("edit-instructions").textContent = "";
            document.getElementById("edit-save-btn").style.display = "none";
        }
    }

    function cancelEditDrawing() {
        // Remove pending marker
        if (editPendingMarker) { map.removeLayer(editPendingMarker); editPendingMarker = null; }
        // Clear drawing
        if (editDrawing.previewLine) { map.removeLayer(editDrawing.previewLine); editDrawing.previewLine = null; }
        if (editDrawing.rubberBand) { map.removeLayer(editDrawing.rubberBand); editDrawing.rubberBand = null; }
        editDrawing.vertices.forEach(function (v) { map.removeLayer(v); });
        editDrawing.vertices = [];
        editDrawing.points = [];
        editDrawing.active = false;
        if (document.getElementById("edit-save-btn")) {
            document.getElementById("edit-save-btn").style.display = "none";
        }
    }

    // ─── Edit existing: select / deselect ────────────────────
    function deselectExistingFeature() {
        if (!editSelected) return;
        // Remove edit vertices
        if (editSelected.editVertices) {
            editSelected.editVertices.forEach(function (v) { map.removeLayer(v); });
        }
        // Restore marker to non-draggable
        if (editSelected.marker) {
            editSelected.marker.dragging.disable();
            editSelected.marker.getElement().classList.remove("edit-highlight");
        }
        // Restore GeoJSON layer style
        if (editSelected.geoLayer) {
            editSelected.geoLayer.eachLayer(function (sub) {
                sub.getElement && sub.getElement() && sub.getElement().classList.remove("edit-highlight-geo");
            });
        }
        editSelected = null;
        if (document.getElementById("edit-save-btn")) {
            document.getElementById("edit-save-btn").style.display = "none";
        }
        document.getElementById("edit-instructions").textContent = "";
    }

    function selectExistingFeature(feature, marker, geoLayer) {
        deselectExistingFeature();
        cancelEditDrawing();
        clearEditSelection(); // deselect type so new creation is disabled

        var originalLatLng = marker ? L.latLng(feature.lat, feature.lon) : null;
        var originalGeojson = geojsonCache[feature.wikidata_id] ? JSON.parse(JSON.stringify(geojsonCache[feature.wikidata_id])) : null;

        editSelected = {
            feature: feature,
            marker: marker,
            geoLayer: geoLayer,
            editVertices: [],
            originalLatLng: originalLatLng,
            originalGeojson: originalGeojson,
        };

        // Highlight marker and make it draggable
        if (marker) {
            marker.dragging.enable();
            if (marker.getElement()) marker.getElement().classList.add("edit-highlight");
        }

        // Highlight GeoJSON and show editable vertices
        if (geoLayer && originalGeojson) {
            geoLayer.eachLayer(function (sub) {
                if (sub.getElement && sub.getElement()) sub.getElement().classList.add("edit-highlight-geo");
            });
            showEditVertices(originalGeojson);
        }

        // Update instructions and show save button
        var langKey = "name_" + LANG;
        var displayName = feature[langKey] || feature.name_en || feature.name;
        document.getElementById("edit-instructions").innerHTML =
            '<strong>' + displayName + '</strong><br>' +
            (_t("mapjs.edit_selected_hint") || "Drag to move. Click Save to edit properties.");
        document.getElementById("edit-save-btn").style.display = "";
    }

    function showEditVertices(geojson) {
        if (!editSelected) return;
        var coords = extractCoords(geojson);
        coords.forEach(function (coord, idx) {
            var latlng = L.latLng(coord[1], coord[0]); // GeoJSON is [lng, lat]
            var vertex = L.circleMarker(latlng, {
                radius: 5, color: "#1a73e8", fillColor: "#fff",
                fillOpacity: 1, weight: 2, className: "edit-vertex",
            }).addTo(map);

            vertex._coordIndex = idx;
            vertex.on("mousedown", function (e) {
                L.DomEvent.stopPropagation(e);
                startVertexDrag(vertex, idx);
            });
            editSelected.editVertices.push(vertex);
        });
    }

    function extractCoords(geojson) {
        if (geojson.type === "LineString") return geojson.coordinates;
        if (geojson.type === "Polygon") return geojson.coordinates[0];
        if (geojson.type === "MultiLineString") return geojson.coordinates[0]; // edit first line
        if (geojson.type === "MultiPolygon") return geojson.coordinates[0][0]; // edit first polygon
        return [];
    }

    function setCoords(geojson, coords) {
        if (geojson.type === "LineString") geojson.coordinates = coords;
        else if (geojson.type === "Polygon") geojson.coordinates[0] = coords;
        else if (geojson.type === "MultiLineString") geojson.coordinates[0] = coords;
        else if (geojson.type === "MultiPolygon") geojson.coordinates[0][0] = coords;
    }

    var dragVertex = null;
    function startVertexDrag(vertex, idx) {
        dragVertex = { vertex: vertex, idx: idx };
        map.dragging.disable();
        map.on("mousemove", onVertexDrag);
        map.once("mouseup", endVertexDrag);
    }

    function onVertexDrag(e) {
        if (!dragVertex || !editSelected) return;
        dragVertex.vertex.setLatLng(e.latlng);
        // Update the GeoJSON coordinate in real time
        var coords = extractCoords(editSelected.originalGeojson);
        coords[dragVertex.idx] = [e.latlng.lng, e.latlng.lat];
        // If polygon and dragging first or last vertex, sync the closure
        if (editSelected.originalGeojson.type === "Polygon" || editSelected.originalGeojson.type === "MultiPolygon") {
            if (dragVertex.idx === 0) coords[coords.length - 1] = [e.latlng.lng, e.latlng.lat];
            else if (dragVertex.idx === coords.length - 1) coords[0] = [e.latlng.lng, e.latlng.lat];
        }
        setCoords(editSelected.originalGeojson, coords);
        // Re-render the GeoJSON layer
        refreshEditGeoLayer();
    }

    function endVertexDrag() {
        map.off("mousemove", onVertexDrag);
        map.dragging.enable();
        dragVertex = null;
    }

    function refreshEditGeoLayer() {
        if (!editSelected || !editSelected.geoLayer || !editSelected.originalGeojson) return;
        // Remove old layer from reliefGeoLayer and re-add
        var f = editSelected.feature;
        var color = RELIEF_TYPE_COLORS[f.type] || "#999";
        var geojson = editSelected.originalGeojson;
        var isLine = (geojson.type === "LineString" || geojson.type === "MultiLineString");
        var style = isLine
            ? { color: color, weight: 4, opacity: 0.8, fillOpacity: 0 }
            : { color: color, weight: 2.5, opacity: 0.8, fillColor: color, fillOpacity: 0.25 };

        reliefGeoLayer.removeLayer(editSelected.geoLayer);
        var newLayer = L.geoJSON(geojson, { style: style });
        newLayer._featureData = f;
        newLayer.eachLayer(function (sub) {
            if (sub.getElement && sub.getElement()) sub.getElement().classList.add("edit-highlight-geo");
        });
        reliefGeoLayer.addLayer(newLayer);
        editSelected.geoLayer = newLayer;
    }

    // Wire existing relief markers for edit-mode click
    function wireReliefMarkerForEdit(marker) {
        marker.on("click", function (e) {
            if (!editMode) return; // normal popup
            L.DomEvent.stopPropagation(e);
            var f = marker._featureData;
            if (!f) return;
            // Find matching GeoJSON layer if any
            var geoLayer = null;
            reliefGeoLayer.eachLayer(function (l) {
                if (l._featureData && l._featureData.wikidata_id === f.wikidata_id) geoLayer = l;
            });
            selectExistingFeature(f, marker, geoLayer);
        });
    }

    function wireReliefGeoLayerForEdit(layer) {
        layer.on("click", function (e) {
            if (!editMode) return;
            L.DomEvent.stopPropagation(e);
            var f = layer._featureData;
            if (!f) return;
            // Find the icon marker in the cluster
            var marker = null;
            reliefCluster.eachLayer(function (m) {
                if (m._featureData && m._featureData.wikidata_id === f.wikidata_id) marker = m;
            });
            selectExistingFeature(f, marker, layer);
        });
    }

    // ─── Edit: Map click handler ────────────────────────────
    map.on("click", function (e) {
        if (!editMode) return;

        // If something is selected and user clicks on empty map, deselect
        if (editSelected && !editSelectedType) {
            deselectExistingFeature();
            return;
        }

        if (!editSelectedType) return;

        if (editDrawing.active) {
            // Add point to drawing
            var pt = [e.latlng.lat, e.latlng.lng];
            editDrawing.points.push(pt);

            // Add vertex marker
            var vertex = L.circleMarker(e.latlng, { radius: 4, color: "#1a73e8", fillColor: "#fff", fillOpacity: 1, weight: 2 });
            vertex.addTo(map);
            editDrawing.vertices.push(vertex);

            // Update preview line
            if (editDrawing.previewLine) map.removeLayer(editDrawing.previewLine);
            editDrawing.previewLine = L.polyline(editDrawing.points, { color: "#1a73e8", weight: 2, dashArray: "5,5" }).addTo(map);
            return;
        }

        // First click: start drawing mode
        editDrawing.active = true;
        editDrawing.points = [[e.latlng.lat, e.latlng.lng]];

        // First vertex
        var vertex = L.circleMarker(e.latlng, { radius: 4, color: "#1a73e8", fillColor: "#fff", fillOpacity: 1, weight: 2 });
        vertex.addTo(map);
        editDrawing.vertices.push(vertex);

        // Show instructions
        var instrEl = document.getElementById("edit-instructions");
        instrEl.textContent = editSelectedType === "river"
            ? (_t("mapjs.edit_draw_line") || "Click to add points. Double-click to finish line.")
            : (_t("mapjs.edit_draw_polygon") || "Click to add points. Double-click to close polygon.");
    });

    // Rubber band on mousemove
    map.on("mousemove", function (e) {
        if (!editMode || !editDrawing.active || editDrawing.points.length === 0) return;
        var lastPt = editDrawing.points[editDrawing.points.length - 1];
        if (editDrawing.rubberBand) map.removeLayer(editDrawing.rubberBand);
        editDrawing.rubberBand = L.polyline([lastPt, [e.latlng.lat, e.latlng.lng]], {
            color: "#1a73e8", weight: 1.5, dashArray: "3,6", opacity: 0.6,
        }).addTo(map);
    });

    // Double click to finish drawing
    map.on("dblclick", function (e) {
        if (!editMode || !editDrawing.active) return;
        L.DomEvent.stopPropagation(e);
        L.DomEvent.preventDefault(e);

        if (editDrawing.points.length < 2) {
            // Too few points — treat as point placement
            var latlng = L.latLng(editDrawing.points[0][0], editDrawing.points[0][1]);
            cancelEditDrawing();
            // Place marker
            editPendingMarker = L.marker(latlng, {
                icon: createReliefSvgIcon(editSelectedType),
                draggable: true,
            }).addTo(map);
            editFormContext = { type: editSelectedType, latlng: latlng, geojson: null, marker: editPendingMarker, existing: null };
            document.getElementById("edit-save-btn").style.display = "";
            return;
        }

        // Build GeoJSON
        var coords, geojson;
        if (editSelectedType === "river") {
            // LineString
            coords = editDrawing.points.map(function (p) { return [p[1], p[0]]; }); // [lng, lat]
            geojson = { type: "LineString", coordinates: coords };
        } else {
            // Polygon — close it
            coords = editDrawing.points.map(function (p) { return [p[1], p[0]]; });
            coords.push(coords[0]); // close ring
            geojson = { type: "Polygon", coordinates: [coords] };
        }

        // Compute centroid for lat/lon
        var sumLat = 0, sumLng = 0;
        editDrawing.points.forEach(function (p) { sumLat += p[0]; sumLng += p[1]; });
        var centroid = L.latLng(sumLat / editDrawing.points.length, sumLng / editDrawing.points.length);

        // Clean up drawing visuals (keep preview line as the shape preview)
        if (editDrawing.rubberBand) { map.removeLayer(editDrawing.rubberBand); editDrawing.rubberBand = null; }
        editDrawing.vertices.forEach(function (v) { map.removeLayer(v); });
        editDrawing.vertices = [];

        // Show finished shape
        if (editDrawing.previewLine) map.removeLayer(editDrawing.previewLine);
        var style = { color: RELIEF_TYPE_COLORS[editSelectedType] || "#1a73e8", weight: 3, opacity: 0.8, fillOpacity: 0.2 };
        editDrawing.previewLine = L.geoJSON(geojson, { style: style }).addTo(map);

        editDrawing.active = false;
        editFormContext = { type: editSelectedType, latlng: centroid, geojson: geojson, marker: null, existing: null };
        document.getElementById("edit-save-btn").style.display = "";
    });

    // ─── Edit form ──────────────────────────────────────────
    var editModalOverlay = document.getElementById("edit-modal-overlay");

    function openEditForm() {
        // If editing an existing feature via selection
        if (editSelected) {
            openEditFormForExisting();
            return;
        }
        if (!editFormContext) return;
        var ctx = editFormContext;

        // Set labels
        document.getElementById("edit-modal-title").textContent = _t("mapjs.edit_mode") || "Edit";
        document.getElementById("edit-tab-new").textContent = _t("mapjs.edit_tab_new") || "Create new";
        document.getElementById("edit-tab-assoc").textContent = _t("mapjs.edit_tab_associate") || "Associate";
        document.getElementById("edit-label-name").textContent = _t("mapjs.edit_name") || "Name";
        document.getElementById("edit-label-type").textContent = _t("mapjs.edit_label_type") || "Type";
        document.getElementById("edit-optional-label").textContent = _t("mapjs.edit_optional") || "Optional fields";
        document.getElementById("edit-label-country").textContent = _t("mapjs.edit_country") || "Country codes";
        document.getElementById("edit-label-search").textContent = _t("mapjs.edit_search") || "Search feature";
        document.getElementById("edit-form-cancel").textContent = _t("mapjs.edit_cancel") || "Cancel";
        document.getElementById("edit-form-submit").textContent = _t("mapjs.edit_save") || "Save";

        // Fill type display
        document.getElementById("edit-type-display").innerHTML =
            '<img src="' + ICON_BASE + ctx.type + '.svg" width="18" height="18" style="vertical-align:middle"> ' + reliefTypeLabel(ctx.type);

        // Fill coordinates
        document.getElementById("edit-lat").value = ctx.latlng.lat.toFixed(5);
        document.getElementById("edit-lon").value = ctx.latlng.lng.toFixed(5);

        // Clear form
        document.getElementById("edit-name").value = "";
        ["es", "en", "fr", "it", "ru"].forEach(function (l) {
            var el = document.getElementById("edit-name-" + l);
            if (el) el.value = "";
        });
        document.getElementById("edit-country").value = "";
        document.getElementById("edit-elev").value = "";
        document.getElementById("edit-length").value = "";
        document.getElementById("edit-area").value = "";
        document.getElementById("edit-search").value = "";
        document.getElementById("edit-search-results").innerHTML = "";
        document.getElementById("edit-selected-feature").style.display = "none";

        // Show "Associate" tab only if we have GeoJSON
        var assocTab = document.getElementById("edit-tab-assoc");
        assocTab.style.display = ctx.geojson ? "" : "none";

        // Activate "new" tab
        switchEditTab("new");

        // Reset submit handler context
        editFormContext.existing = null;

        editModalOverlay.classList.add("active");
    }

    function openEditFormForExisting() {
        var f = editSelected.feature;

        // Set labels
        document.getElementById("edit-modal-title").textContent = (_t("mapjs.edit_editing") || "Editing") + ": " +
            (f["name_" + LANG] || f.name_en || f.name);
        document.getElementById("edit-tab-new").textContent = _t("mapjs.edit_properties") || "Properties";
        document.getElementById("edit-label-name").textContent = _t("mapjs.edit_name") || "Name";
        document.getElementById("edit-label-type").textContent = _t("mapjs.edit_label_type") || "Type";
        document.getElementById("edit-optional-label").textContent = _t("mapjs.edit_optional") || "Optional fields";
        document.getElementById("edit-label-country").textContent = _t("mapjs.edit_country") || "Country codes";
        document.getElementById("edit-form-cancel").textContent = _t("mapjs.edit_cancel") || "Cancel";
        document.getElementById("edit-form-submit").textContent = _t("mapjs.edit_save") || "Save";

        // Fill type display
        document.getElementById("edit-type-display").innerHTML =
            '<img src="' + ICON_BASE + f.type + '.svg" width="18" height="18" style="vertical-align:middle"> ' + reliefTypeLabel(f.type);

        // Pre-fill form with existing data
        document.getElementById("edit-name").value = f.name || "";
        document.getElementById("edit-lat").value = editSelected.marker
            ? editSelected.marker.getLatLng().lat.toFixed(5)
            : f.lat.toFixed(5);
        document.getElementById("edit-lon").value = editSelected.marker
            ? editSelected.marker.getLatLng().lng.toFixed(5)
            : f.lon.toFixed(5);

        ["es", "en", "fr", "it", "ru"].forEach(function (l) {
            var el = document.getElementById("edit-name-" + l);
            if (el) el.value = f["name_" + l] || "";
        });
        document.getElementById("edit-country").value = f.country_codes || "";
        document.getElementById("edit-elev").value = f.elevation_m != null ? f.elevation_m : "";
        document.getElementById("edit-length").value = f.length_km != null ? f.length_km : "";
        document.getElementById("edit-area").value = f.area_km2 != null ? f.area_km2 : "";

        // Hide associate tab, show only properties
        document.getElementById("edit-tab-assoc").style.display = "none";
        switchEditTab("new");

        // Set context so submit knows this is an update
        editFormContext = {
            type: f.type,
            latlng: L.latLng(f.lat, f.lon),
            geojson: editSelected.originalGeojson,
            marker: editSelected.marker,
            existing: f,
        };

        editModalOverlay.classList.add("active");
    }

    function closeEditForm() {
        editModalOverlay.classList.remove("active");
    }

    // Tab switching
    function switchEditTab(tab) {
        document.querySelectorAll(".edit-tab").forEach(function (t) { t.classList.toggle("active", t.dataset.tab === tab); });
        document.getElementById("edit-pane-new").style.display = tab === "new" ? "" : "none";
        document.getElementById("edit-pane-assoc").style.display = tab === "associate" ? "" : "none";
    }

    document.getElementById("edit-tab-new").addEventListener("click", function () { switchEditTab("new"); });
    document.getElementById("edit-tab-assoc").addEventListener("click", function () { switchEditTab("associate"); });
    document.getElementById("edit-modal-close").addEventListener("click", closeEditForm);
    document.getElementById("edit-form-cancel").addEventListener("click", function () {
        closeEditForm();
        cancelEditDrawing();
    });

    editModalOverlay.addEventListener("click", function (e) { if (e.target === editModalOverlay) closeEditForm(); });

    // Search for existing features (associate tab)
    var searchTimeout = null;
    document.getElementById("edit-search").addEventListener("input", function () {
        clearTimeout(searchTimeout);
        var val = this.value.toLowerCase().trim();
        searchTimeout = setTimeout(function () {
            var resultsEl = document.getElementById("edit-search-results");
            if (val.length < 2) { resultsEl.innerHTML = ""; return; }
            var matches = allReliefFeatures.filter(function (f) {
                if (f.has_geojson) return false;
                var name = (f["name_" + LANG] || f.name_en || f.name || "").toLowerCase();
                return name.indexOf(val) >= 0;
            }).slice(0, 10);
            resultsEl.innerHTML = matches.map(function (f) {
                var name = f["name_" + LANG] || f.name_en || f.name;
                return '<div class="edit-search-item" data-wid="' + f.wikidata_id + '">' +
                    '<img src="' + ICON_BASE + f.type + '.svg" width="16" height="16"> ' + name +
                    ' <span class="edit-search-type">' + reliefTypeLabel(f.type) + '</span></div>';
            }).join("");

            resultsEl.querySelectorAll(".edit-search-item").forEach(function (el) {
                el.addEventListener("click", function () {
                    var wid = el.dataset.wid;
                    var feat = allReliefFeatures.find(function (f) { return f.wikidata_id === wid; });
                    if (feat) {
                        editFormContext.associateWith = feat;
                        document.getElementById("edit-selected-feature").style.display = "";
                        document.getElementById("edit-selected-feature").innerHTML =
                            '<img src="' + ICON_BASE + feat.type + '.svg" width="18" height="18"> ' +
                            (feat["name_" + LANG] || feat.name_en || feat.name);
                        resultsEl.innerHTML = "";
                        document.getElementById("edit-search").value = "";
                    }
                });
            });
        }, 200);
    });

    // Submit
    document.getElementById("edit-form-submit").addEventListener("click", function () {
        if (!editFormContext) return;
        var ctx = editFormContext;

        // ── Update existing feature ──
        if (ctx.existing) {
            var payload = {};
            var nameVal = document.getElementById("edit-name").value.trim();
            if (nameVal && nameVal !== ctx.existing.name) payload.name = nameVal;

            var lat = parseFloat(document.getElementById("edit-lat").value);
            var lon = parseFloat(document.getElementById("edit-lon").value);
            if (lat !== ctx.existing.lat) payload.lat = lat;
            if (lon !== ctx.existing.lon) payload.lon = lon;

            ["es", "en", "fr", "it", "ru"].forEach(function (l) {
                var v = document.getElementById("edit-name-" + l).value.trim();
                if (v !== (ctx.existing["name_" + l] || "")) payload["name_" + l] = v;
            });
            var cc = document.getElementById("edit-country").value.trim();
            if (cc !== (ctx.existing.country_codes || "")) payload.country_codes = cc;
            var elev = document.getElementById("edit-elev").value;
            if (elev !== "" && parseFloat(elev) !== ctx.existing.elevation_m) payload.elevation_m = parseFloat(elev);
            var len = document.getElementById("edit-length").value;
            if (len !== "" && parseFloat(len) !== ctx.existing.length_km) payload.length_km = parseFloat(len);
            var area = document.getElementById("edit-area").value;
            if (area !== "" && parseFloat(area) !== ctx.existing.area_km2) payload.area_km2 = parseFloat(area);

            // Include updated GeoJSON if it was modified
            if (editSelected && editSelected.originalGeojson) {
                payload.geojson = editSelected.originalGeojson;
            }

            // If marker was dragged, use its position
            if (editSelected && editSelected.marker) {
                var mll = editSelected.marker.getLatLng();
                payload.lat = mll.lat;
                payload.lon = mll.lng;
            }

            fetch("/api/relief-features/" + ctx.existing.wikidata_id, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            }).then(function (r) { return r.json(); }).then(function (updated) {
                // Update local data
                for (var i = 0; i < allReliefFeatures.length; i++) {
                    if (allReliefFeatures[i].wikidata_id === updated.wikidata_id) {
                        allReliefFeatures[i] = updated;
                        break;
                    }
                }
                if (editSelected && editSelected.originalGeojson) {
                    geojsonCache[updated.wikidata_id] = editSelected.originalGeojson;
                }
                // Rebuild map layers
                closeEditForm();
                deselectExistingFeature();
                rebuildReliefMarkers();
            }).catch(function (err) { console.error("Error updating feature:", err); });
            return;
        }

        // ── Associate GeoJSON with existing feature ──
        var activeTab = document.querySelector(".edit-tab.active").dataset.tab;

        if (activeTab === "associate" && ctx.associateWith && ctx.geojson) {
            fetch("/api/relief-features/" + ctx.associateWith.wikidata_id + "/geojson", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ geojson: ctx.geojson }),
            }).then(function (r) { return r.json(); }).then(function (res) {
                if (res.status === "ok") {
                    ctx.associateWith.has_geojson = true;
                    geojsonCache[ctx.associateWith.wikidata_id] = ctx.geojson;
                    showReliefGeoJsonInView();
                    closeEditForm();
                    cancelEditDrawing();
                }
            }).catch(function (err) { console.error("Error associating GeoJSON:", err); });
            return;
        }

        // ── Create new feature ──
        var nameVal = document.getElementById("edit-name").value.trim();
        if (!nameVal) { document.getElementById("edit-name").focus(); return; }

        var payload = {
            name: nameVal,
            type: ctx.type,
            lat: parseFloat(document.getElementById("edit-lat").value),
            lon: parseFloat(document.getElementById("edit-lon").value),
        };

        ["es", "en", "fr", "it", "ru"].forEach(function (l) {
            var v = document.getElementById("edit-name-" + l).value.trim();
            if (v) payload["name_" + l] = v;
        });

        var cc = document.getElementById("edit-country").value.trim();
        if (cc) payload.country_codes = cc;
        var elev = document.getElementById("edit-elev").value;
        if (elev) payload.elevation_m = parseFloat(elev);
        var len = document.getElementById("edit-length").value;
        if (len) payload.length_km = parseFloat(len);
        var area = document.getElementById("edit-area").value;
        if (area) payload.area_km2 = parseFloat(area);
        if (ctx.geojson) payload.geojson = ctx.geojson;

        fetch("/api/relief-features", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        }).then(function (r) { return r.json(); }).then(function (newFeature) {
            allReliefFeatures.push(newFeature);
            if (newFeature.has_geojson && ctx.geojson) {
                geojsonCache[newFeature.wikidata_id] = ctx.geojson;
            }
            if (reliefVisible && activeReliefTypes.has(newFeature.type)) {
                reliefCluster.addLayer(createReliefIconMarker(newFeature));
                if (newFeature.has_geojson) showReliefGeoJsonInView();
            }
            closeEditForm();
            cancelEditDrawing();
        }).catch(function (err) { console.error("Error creating feature:", err); });
    });

    // ─── Map events ─────────────────────────────────────────
    map.on("zoomend", function () {
        updateCityVisibility();
        updateCountryBordersForZoom();
        applyTileForZoom();
        checkAndLoadTiles();
    });

    var viewTimer = null;
    map.on("moveend", function () {
        clearTimeout(viewTimer);
        viewTimer = setTimeout(function () {
            updateCountryBordersForZoom();
            if (reliefVisible) showReliefGeoJsonInView();
            checkAndLoadTiles();
        }, 200);
    });

    // ─── Init ───────────────────────────────────────────────
    async function init() {
        var loading = document.getElementById("loading");
        try {
            var [countriesResp, geojsonResp, baseResp, indexResp, reliefResp] = await Promise.all([
                fetch("/api/countries"),
                fetch("/api/geojson/all"),
                fetch(TILE_BASE + "base.json"),
                fetch(TILE_BASE + "index.json"),
                fetch("/api/relief-features"),
            ]);

            var countries = await countriesResp.json();
            var geojsonData = await geojsonResp.json();
            var baseCities = await baseResp.json();
            var indexData = await indexResp.json();
            allReliefFeatures = await reliefResp.json();

            console.log("[GeoFreak] Data loaded. base:", baseCities.length, "cities, tiles:", indexData.tiles.length);

            // Tile index
            tileZoom = indexData.z;
            tileIndex = new Set(indexData.tiles);

            // Index countries by ISO
            countries.forEach(function (c) {
                if (c.iso_a3) countriesData[c.iso_a3] = c;
            });

            // Country borders
            countryGeoLayer = L.geoJSON(geojsonData, {
                style: defaultStyle,
                onEachFeature: onEachCountryFeature,
            }).addTo(map);

            // Base city markers (capitals + 500K+)
            addCityMarkers(baseCities);
            console.log("[GeoFreak] Markers added.",
                "capitals=" + cityLayers.capitals.getLayers().length,
                "mega=" + cityLayers.mega.getLayers().length,
                "large=" + cityLayers.large.getLayers().length
            );

            // Relief cluster
            reliefCluster = L.markerClusterGroup({
                maxClusterRadius: 40,
                spiderfyOnMaxZoom: true,
                showCoverageOnHover: false,
                zoomToBoundsOnClick: true,
                disableClusteringAtZoom: 12,
            });

            // Build UI controls
            buildLayersControl();
            buildEditControl();
            buildEditPanel();

            // Apply initial preset (political)
            applyPreset("political");

            // Verify layers are on map
            console.log("[GeoFreak] After applyPreset. zoom=" + map.getZoom(),
                "capitals on map:", map.hasLayer(cityLayers.capitals),
                "capitals count:", cityLayers.capitals.getLayers().length,
                "mega count:", cityLayers.mega.getLayers().length,
                "large count:", cityLayers.large.getLayers().length
            );

            // Load visible tiles at current zoom
            checkAndLoadTiles();

        } catch (err) {
            console.error("Error loading map data:", err, err.stack);
        } finally {
            if (loading) {
                loading.classList.add("hidden");
                setTimeout(function () { loading.remove(); }, 500);
            }
        }
    }

    init();
})();
