/**
 * GeoFreak — Unified Interactive Map
 * Political (countries + cities) + Physical (relief features) with presets
 */

(function () {
    "use strict";

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
    var starSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="SIZE" height="SIZE">' +
        '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14l-5-4.87 6.91-1.01L12 2z" ' +
        'fill="FILL" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';

    function makeCapitalIcon(pop) {
        var size = pop >= 5000000 ? 22 : pop >= 1000000 ? 18 : 14;
        var fill = "%23222";
        var svg = starSvg.replace(/SIZE/g, size).replace("FILL", fill);
        var encoded = "data:image/svg+xml," + encodeURIComponent(svg).replace(/%23/g, "%23");
        return L.icon({ iconUrl: encoded, iconSize: [size, size], iconAnchor: [size / 2, size / 2], popupAnchor: [0, -size / 2] });
    }

    function makeCityIcon(pop) {
        var size, cls;
        if (pop >= 5000000)      { size = 12; cls = "city-marker-mega"; }
        else if (pop >= 1000000) { size = 9;  cls = "city-marker-1m"; }
        else if (pop >= 500000)  { size = 7;  cls = "city-marker-500k"; }
        else if (pop >= 100000)  { size = 5;  cls = "city-marker-100k"; }
        else                     { size = 3;  cls = "city-marker-small"; }
        return L.divIcon({ className: cls, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
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
            var icon = isCapital ? makeCapitalIcon(pop) : makeCityIcon(pop);
            var marker = L.marker([city.lat, city.lon], {
                icon: icon,
                zIndexOffset: isCapital ? 1000 : (pop >= 5000000 ? 500 : 0),
            });
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
        capitals: 3, mega: 2, large: 3, medium: 4, small100k: 5, tiny: 7,
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

    // ─── Preset system ──────────────────────────────────────
    var presetButtons = document.querySelectorAll(".map-preset");
    var customPanel = document.getElementById("custom-panel");
    var currentPreset = "political";

    // Layer state tracks which logical layers are enabled
    var layerState = {
        countries: true, capitals: true, mega: true, large: true,
        medium: true, small100k: false, tiny: false,
        reliefAll: false, reliefLand: false, reliefWater: false, reliefCoast: false,
    };

    // Custom state (remembers last custom config)
    var customState = JSON.parse(JSON.stringify(layerState));

    var presets = {
        political: {
            tile: "light", countries: true, capitals: true, mega: true,
            large: true, medium: true, small100k: false, tiny: false,
            reliefAll: false, reliefLand: false, reliefWater: false, reliefCoast: false,
        },
        physical: {
            tile: "physical", countries: false, capitals: false, mega: false,
            large: false, medium: false, small100k: false, tiny: false,
            reliefAll: true, reliefLand: false, reliefWater: false, reliefCoast: false,
        },
    };

    function applyPreset(name) {
        currentPreset = name;
        var p = name === "custom" ? customState : presets[name];

        // Switch tile
        if (p.tile) setTileLayer(p.tile);

        // Countries
        layerState.countries = p.countries;
        if (countryGeoLayer) {
            if (p.countries && !map.hasLayer(countryGeoLayer)) map.addLayer(countryGeoLayer);
            else if (!p.countries && map.hasLayer(countryGeoLayer)) map.removeLayer(countryGeoLayer);
        }

        // Cities
        ["capitals", "mega", "large", "medium", "small100k", "tiny"].forEach(function (k) {
            layerState[k] = p[k];
        });
        updateCityVisibility();

        // Relief
        layerState.reliefAll = p.reliefAll;
        layerState.reliefLand = p.reliefLand;
        layerState.reliefWater = p.reliefWater;
        layerState.reliefCoast = p.reliefCoast;
        updateReliefFromState();

        // Preset buttons
        presetButtons.forEach(function (btn) {
            btn.classList.toggle("active", btn.dataset.preset === name);
        });

        // Custom panel
        if (name === "custom") {
            customPanel.classList.add("visible");
            syncCustomCheckboxes();
        } else {
            customPanel.classList.remove("visible");
        }
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

    // Sync checkboxes in custom panel to match current layerState
    function syncCustomCheckboxes() {
        var checkboxMap = {
            countries: "countries", capitals: "capitals",
            cities5m: "mega", cities1m: "large", cities500k: "medium",
            cities100k: "small100k", citiesOther: "tiny",
            reliefAll: "reliefAll", reliefLand: "reliefLand",
            reliefWater: "reliefWater", reliefCoast: "reliefCoast",
        };
        customPanel.querySelectorAll("input[type=checkbox]").forEach(function (cb) {
            var layerKey = checkboxMap[cb.dataset.layer];
            if (layerKey !== undefined) cb.checked = layerState[layerKey];
        });
    }

    // Preset button click handlers
    presetButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var preset = btn.dataset.preset;
            if (preset === "custom" && currentPreset === "custom") {
                // Toggle panel
                customPanel.classList.toggle("visible");
                return;
            }
            applyPreset(preset);
        });
    });

    // Custom panel checkbox handlers
    if (customPanel) {
        var checkboxMap = {
            countries: "countries", capitals: "capitals",
            cities5m: "mega", cities1m: "large", cities500k: "medium",
            cities100k: "small100k", citiesOther: "tiny",
            reliefAll: "reliefAll", reliefLand: "reliefLand",
            reliefWater: "reliefWater", reliefCoast: "reliefCoast",
        };

        customPanel.querySelectorAll("input[type=checkbox]").forEach(function (cb) {
            cb.addEventListener("change", function () {
                // Switch to custom preset when user toggles a checkbox
                if (currentPreset !== "custom") {
                    currentPreset = "custom";
                    presetButtons.forEach(function (b) {
                        b.classList.toggle("active", b.dataset.preset === "custom");
                    });
                }

                var layerKey = checkboxMap[cb.dataset.layer];
                if (layerKey === undefined) return;

                layerState[layerKey] = cb.checked;
                customState[layerKey] = cb.checked;

                // Handle "reliefAll" toggling individual subcategories
                if (cb.dataset.layer === "reliefAll" && cb.checked) {
                    layerState.reliefLand = false;
                    layerState.reliefWater = false;
                    layerState.reliefCoast = false;
                    customState.reliefLand = false;
                    customState.reliefWater = false;
                    customState.reliefCoast = false;
                    syncCustomCheckboxes();
                } else if (["reliefLand", "reliefWater", "reliefCoast"].indexOf(layerKey) >= 0 && cb.checked) {
                    layerState.reliefAll = false;
                    customState.reliefAll = false;
                    syncCustomCheckboxes();
                }

                // Apply changes
                if (layerKey === "countries") {
                    if (countryGeoLayer) {
                        if (cb.checked) map.addLayer(countryGeoLayer);
                        else map.removeLayer(countryGeoLayer);
                    }
                } else if (["capitals", "mega", "large", "medium", "small100k", "tiny"].indexOf(layerKey) >= 0) {
                    updateCityVisibility();
                } else {
                    updateReliefFromState();
                }
            });
        });
    }

    // Close custom panel on outside click
    document.addEventListener("click", function (e) {
        if (currentPreset === "custom" && customPanel.classList.contains("visible")) {
            if (!customPanel.contains(e.target) && !e.target.closest('.map-preset[data-preset="custom"]')) {
                customPanel.classList.remove("visible");
            }
        }
    });

    // ─── Map events ─────────────────────────────────────────
    map.on("zoomend", function () {
        updateCityVisibility();
        applyTileForZoom();
    });

    var viewTimer = null;
    map.on("moveend", function () {
        clearTimeout(viewTimer);
        viewTimer = setTimeout(function () {
            if (reliefVisible) showReliefGeoJsonInView();
        }, 200);
    });

    // ─── Init ───────────────────────────────────────────────
    async function init() {
        var loading = document.getElementById("loading");
        try {
            var [countriesResp, geojsonResp, citiesResp, reliefResp] = await Promise.all([
                fetch("/api/countries"),
                fetch("/api/geojson/all"),
                fetch("/api/cities"),
                fetch("/api/relief-features"),
            ]);

            var countries = await countriesResp.json();
            var geojsonData = await geojsonResp.json();
            var cities = await citiesResp.json();
            allReliefFeatures = await reliefResp.json();

            // Index countries by ISO
            countries.forEach(function (c) {
                if (c.iso_a3) countriesData[c.iso_a3] = c;
            });

            // Country borders
            countryGeoLayer = L.geoJSON(geojsonData, {
                style: defaultStyle,
                onEachFeature: onEachCountryFeature,
            }).addTo(map);

            // City markers
            addCityMarkers(cities);

            // Relief cluster
            reliefCluster = L.markerClusterGroup({
                maxClusterRadius: 40,
                spiderfyOnMaxZoom: true,
                showCoverageOnHover: false,
                zoomToBoundsOnClick: true,
                disableClusteringAtZoom: 12,
            });

            // Apply initial preset (political)
            applyPreset("political");

        } catch (err) {
            console.error("Error loading map data:", err);
        } finally {
            if (loading) {
                loading.classList.add("hidden");
                setTimeout(function () { loading.remove(); }, 500);
            }
        }
    }

    init();
})();
