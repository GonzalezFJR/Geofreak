/**
 * GeoFreak — Interactive Map Viewer
 * Leaflet + GeoJSON + multi-layer cities + country modals
 */

(function () {
    "use strict";

    // ─── Map setup ──────────────────────────────────────────
    const map = L.map("map", {
        center: [20, 0],
        zoom: 3,
        minZoom: 2,
        maxZoom: 18,
        zoomControl: true,
        worldCopyJump: true,
    });

    // ─── Tile layers ────────────────────────────────────────
    const tileLayers = {
        [T['mapjs.layer_flat'] || 'Light']: L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
            {
                attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://osm.org/">OSM</a>',
                subdomains: "abcd",
                maxZoom: 20,
            }
        ),
        [T['mapjs.layer_standard'] || 'Standard']: L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            {
                attribution: '&copy; <a href="https://openstreetmap.org/">OpenStreetMap</a>',
                maxZoom: 19,
            }
        ),
        [T['mapjs.layer_satellite'] || 'Satellite']: L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            {
                attribution: '&copy; <a href="https://www.esri.com/">Esri</a>',
                maxZoom: 18,
            }
        ),
        [T['mapjs.layer_dark'] || 'Dark']: L.tileLayer(
            "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
            {
                attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
                subdomains: "abcd",
                maxZoom: 20,
            }
        ),
    };

    tileLayers[T['mapjs.layer_flat'] || 'Light'].addTo(map);

    // ─── City layers (by zoom level) ────────────────────────
    // Layer groups for different city tiers
    const cityLayers = {
        capitals: L.layerGroup(),       // Capitals — always visible from zoom 3+
        megacities: L.layerGroup(),      // 5M+ — visible from zoom 3+
        large: L.layerGroup(),           // 1M–5M — visible from zoom 4+
        medium: L.layerGroup(),          // 500K–1M — visible from zoom 5+
        small: L.layerGroup(),           // <500K — visible from zoom 6+
    };

    // Overlay control labels
    const overlays = {
        [T['mapjs.capitals'] || '⭐ Capitals']: cityLayers.capitals,
        [T['mapjs.megacities'] || '🔴 Megacities (5M+)']: cityLayers.megacities,
        [T['mapjs.large_cities'] || '🟠 Large cities (1M+)']: cityLayers.large,
        [T['mapjs.medium_cities'] || '🟡 Medium cities (500K+)']: cityLayers.medium,
        [T['mapjs.other_cities'] || '⚪ Other cities']: cityLayers.small,
    };

    // Add layer control
    L.control.layers(tileLayers, overlays, { position: "topright", collapsed: true }).addTo(map);

    // ─── State ──────────────────────────────────────────────
    let countriesData = {};
    let geojsonLayer = null;
    let highlightedLayer = null;

    // ─── Helpers ────────────────────────────────────────────
    function formatNumber(n) {
        if (n === "" || n === null || n === undefined) return "—";
        const num = Number(n);
        if (isNaN(num)) return n;
        var locale = window.LANG === 'en' ? 'en-US' : 'es-ES';
        if (num >= 1e12) return (num / 1e12).toFixed(2) + " T";
        if (num >= 1e9) return (num / 1e9).toFixed(2) + " B";
        if (num >= 1e6) return (num / 1e6).toFixed(2) + " M";
        if (num >= 1e3) return num.toLocaleString(locale);
        return String(num);
    }

    function formatPop(n) {
        if (!n || n <= 0) return "";
        var u = T['mapjs.inhabitants'] || 'inhab.';
        if (n >= 1e6) return (n / 1e6).toFixed(1) + "M " + u;
        if (n >= 1e3) return Math.round(n / 1e3) + "K " + u;
        return n + " " + u;
    }

    function flagUrl(iso3) {
        return "/static/data/images/flags/" + iso3 + ".svg";
    }

    function flagUrlFallback(iso3) {
        return "/static/data/images/flags/" + iso3 + ".png";
    }

    // ─── GeoJSON styling ────────────────────────────────────
    function defaultStyle() {
        return {
            fillColor: "#1a73e8",
            fillOpacity: 0.12,
            color: "#1a73e8",
            weight: 1.2,
            opacity: 0.6,
        };
    }

    function highlightStyle() {
        return {
            fillColor: "#1a73e8",
            fillOpacity: 0.35,
            color: "#0d47a1",
            weight: 2.5,
            opacity: 1,
        };
    }

    function getIso3(feature) {
        var p = feature.properties || {};
        return p.ISO_A3 || p.iso_a3 || p.ADM0_A3 || p.adm0_a3 || "";
    }

    function getCountryName(feature) {
        var p = feature.properties || {};
        return p.ADMIN || p.admin || p.name || p.NAME || p.GEOUNIT || "";
    }

    function onEachFeature(feature, layer) {
        var iso3 = getIso3(feature);
        var name = getCountryName(feature);
        var country = countriesData[iso3] || {};
        var capital = country.capital || "";

        var tooltipContent =
            '<div class="country-tooltip">' +
            '<div class="tooltip-name">' + (country.name || name) + '</div>' +
            (capital ? '<div class="tooltip-capital">🏛️ ' + capital + '</div>' : '') +
            '</div>';

        layer.bindTooltip(tooltipContent, {
            sticky: true,
            className: "country-tooltip-wrapper",
            direction: "top",
            offset: [0, -10],
        });

        layer.on("mouseover", function () {
            if (highlightedLayer !== layer) {
                layer.setStyle(highlightStyle());
                layer.bringToFront();
            }
        });

        layer.on("mouseout", function () {
            if (highlightedLayer !== layer) {
                geojsonLayer.resetStyle(layer);
            }
        });

        layer.on("click", function () {
            if (highlightedLayer && highlightedLayer !== layer) {
                geojsonLayer.resetStyle(highlightedLayer);
            }
            highlightedLayer = layer;
            layer.setStyle(highlightStyle());
            showCountryModal(iso3, name);
        });
    }

    // ─── Modal ──────────────────────────────────────────────
    var modalOverlay = document.getElementById("modal-overlay");
    var modalClose = document.getElementById("modal-close");

    function closeModal() {
        modalOverlay.classList.remove("active");
        if (highlightedLayer) {
            geojsonLayer.resetStyle(highlightedLayer);
            highlightedLayer = null;
        }
    }

    modalClose.addEventListener("click", closeModal);
    modalOverlay.addEventListener("click", function (e) {
        if (e.target === modalOverlay) closeModal();
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") closeModal();
    });

    function showCountryModal(iso3, fallbackName) {
        var c = countriesData[iso3] || {};
        var name = c.name || fallbackName;

        var flagImg = document.getElementById("modal-flag");
        flagImg.src = flagUrl(iso3);
        flagImg.onerror = function () {
            this.src = flagUrlFallback(iso3);
            this.onerror = function () {
                this.src = "";
                this.style.display = "none";
            };
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
            return '<div class="modal-item">' +
                '<span class="modal-item-label">' + label + '</span>' +
                '<span class="modal-item-value">' + value + '</span>' +
                '</div>';
        }

        var languages = "";
        try {
            var langs = typeof c.official_languages === "string"
                ? JSON.parse(c.official_languages) : c.official_languages;
            if (Array.isArray(langs)) languages = langs.join(", ");
        } catch (e) {
            languages = c.official_languages || "";
        }

        // Top cities section
        var citiesHtml = "";
        try {
            var topCities = typeof c.top_cities === "string"
                ? JSON.parse(c.top_cities) : c.top_cities;
            if (Array.isArray(topCities) && topCities.length > 0) {
                citiesHtml = '<div class="modal-section">' +
                    '<div class="modal-section-title">' + (T['mapjs.top_cities'] || '🏙️ Top cities') + '</div>' +
                    '<div class="modal-grid">';
                topCities.forEach(function (city) {
                    var badge = city.is_capital ? ' <span style="color:var(--blue-500);font-size:0.75rem;">⭐</span>' : '';
                    citiesHtml += item(
                        city.name + badge,
                        formatNumber(city.population) + " " + (T['mapjs.inhabitants'] || 'inhab.')
                    );
                });
                citiesHtml += '</div></div>';
            }
        } catch (e) { /* ignore */ }

        var _t = function(k) { return T[k] || k; };

        return '<div class="modal-section">' +
            '<div class="modal-section-title">' + _t('mapjs.section_general') + '</div>' +
            '<div class="modal-grid">' +
            item(_t("mapjs.capital"), c.capital) +
            item(_t("mapjs.region"), c.region) +
            item(_t("mapjs.subregion"), c.subregion) +
            item(_t("mapjs.continent"), c.continent) +
            item(_t("mapjs.lat_lon"), c.lat && c.lon ? Number(c.lat).toFixed(2) + "° / " + Number(c.lon).toFixed(2) + "°" : "") +
            item(_t("mapjs.timezone"), c.timezones) +
            item("ISO", c.iso_a2 + " / " + c.iso_a3) +
            item(_t("mapjs.domain"), c.tld) +
            '</div></div>' +

            '<div class="modal-section">' +
            '<div class="modal-section-title">' + _t('mapjs.section_population') + '</div>' +
            '<div class="modal-grid">' +
            item(_t("mapjs.population"), formatNumber(c.population)) +
            item(_t("mapjs.area"), c.area_km2 ? formatNumber(c.area_km2) + " km²" : "") +
            item(_t("mapjs.density"), c.density_per_km2 ? Number(c.density_per_km2).toFixed(1) + " hab/km²" : "") +
            item(_t("mapjs.birth_rate"), c.birth_rate ? Number(c.birth_rate).toFixed(1) + " ‰" : "") +
            item(_t("mapjs.immigrant_pct"), c.immigrant_pct ? Number(c.immigrant_pct).toFixed(1) + "%" : "") +
            item(_t("mapjs.life_expectancy"), c.life_expectancy ? Number(c.life_expectancy).toFixed(1) + (window.LANG === 'en' ? ' years' : ' años') : "") +
            item(_t("mapjs.urban_pop"), c.urban_population_pct ? Number(c.urban_population_pct).toFixed(1) + "%" : "") +
            item(_t("mapjs.literacy"), c.literacy_rate ? Number(c.literacy_rate).toFixed(1) + "%" : "") +
            '</div></div>' +

            citiesHtml +

            '<div class="modal-section">' +
            '<div class="modal-section-title">' + _t('mapjs.section_economy') + '</div>' +
            '<div class="modal-grid">' +
            item(_t("mapjs.gdp"), c.gdp_usd ? "$" + formatNumber(c.gdp_usd) : "") +
            item(_t("mapjs.gdp_per_capita"), c.gdp_per_capita_usd ? "$" + formatNumber(c.gdp_per_capita_usd) : "") +
            item(_t("mapjs.gini"), c.gini || "") +
            item(_t("mapjs.hdi"), c.hdi || "") +
            item(_t("mapjs.currency"), c.currency_name ? c.currency_name + " (" + c.currency_code + ")" : "") +
            '</div></div>' +

            '<div class="modal-section">' +
            '<div class="modal-section-title">' + _t('mapjs.section_languages') + '</div>' +
            '<div class="modal-grid">' +
            item(_t("mapjs.main_language"), c.main_language) +
            item(_t("mapjs.secondary_language"), c.secondary_language) +
            item(_t("mapjs.official_languages"), languages) +
            item(_t("mapjs.car_side"), c.car_side) +
            item(_t("mapjs.start_of_week"), c.start_of_week) +
            '</div></div>' +

            '<div class="modal-section">' +
            '<div class="modal-section-title">' + _t('mapjs.section_links') + '</div>' +
            '<div class="modal-grid">' +
            (c.google_maps ? '<div class="modal-item"><a href="' + c.google_maps + '" target="_blank" rel="noopener" style="color:var(--blue-500);">' + _t('mapjs.google_maps') + '</a></div>' : '') +
            (c.osm_maps ? '<div class="modal-item"><a href="' + c.osm_maps + '" target="_blank" rel="noopener" style="color:var(--blue-500);">' + _t('mapjs.osm') + '</a></div>' : '') +
            '</div></div>';
    }

    // ─── City markers ───────────────────────────────────────

    // Star SVG for capitals (inline data URI)
    var starSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="SIZE" height="SIZE">' +
        '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 22 12 18.56 5.82 22 7 14.14l-5-4.87 6.91-1.01L12 2z" ' +
        'fill="FILL" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';

    function makeCapitalIcon(pop) {
        var size = pop >= 5000000 ? 22 : pop >= 1000000 ? 18 : 14;
        var fill = "%23d4a017"; // gold
        var svg = starSvg.replace(/SIZE/g, size).replace("FILL", fill);
        var encoded = "data:image/svg+xml," + encodeURIComponent(svg).replace(/%23/g, "%23");
        return L.icon({
            iconUrl: encoded,
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
            popupAnchor: [0, -size / 2],
        });
    }

    function makeCityIcon(pop) {
        var isLarge = pop >= 1000000;
        var size = pop >= 5000000 ? 10 : pop >= 1000000 ? 7 : pop >= 500000 ? 5 : 4;
        return L.divIcon({
            className: isLarge ? "city-marker-large" : "city-marker",
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
        });
    }

    function cityTooltipHtml(city) {
        return '<div class="city-tooltip-content">' +
            '<div class="ct-name">' + city.name +
            (city.is_capital ? '<span class="ct-badge">' + (T['mapjs.capital_badge'] || 'CAPITAL') + '</span>' : '') +
            '</div>' +
            '<div class="ct-country">' + city.country + '</div>' +
            (city.population > 0 ? '<div class="ct-pop">' + formatPop(city.population) + '</div>' : '') +
            '</div>';
    }

    function addCityMarkers(cities) {
        cities.forEach(function (city) {
            if (!city.lat || !city.lon) return;

            var pop = city.population || 0;
            var isCapital = city.is_capital;

            // Create marker
            var icon = isCapital ? makeCapitalIcon(pop) : makeCityIcon(pop);
            var marker = L.marker([city.lat, city.lon], {
                icon: icon,
                zIndexOffset: isCapital ? 1000 : (pop >= 5000000 ? 500 : 0),
            });

            marker.bindTooltip(cityTooltipHtml(city), {
                direction: "top",
                offset: [0, -8],
                className: "country-tooltip-wrapper",
            });

            // Place in appropriate layer group
            if (isCapital) {
                cityLayers.capitals.addLayer(marker);
            } else if (pop >= 5000000) {
                cityLayers.megacities.addLayer(marker);
            } else if (pop >= 1000000) {
                cityLayers.large.addLayer(marker);
            } else if (pop >= 500000) {
                cityLayers.medium.addLayer(marker);
            } else {
                cityLayers.small.addLayer(marker);
            }
        });
    }

    // ─── Zoom-based layer visibility ────────────────────────
    function updateLayerVisibility() {
        var zoom = map.getZoom();

        // Capitals + megacities: zoom >= 3
        if (zoom >= 3) {
            if (!map.hasLayer(cityLayers.capitals)) map.addLayer(cityLayers.capitals);
            if (!map.hasLayer(cityLayers.megacities)) map.addLayer(cityLayers.megacities);
        } else {
            if (map.hasLayer(cityLayers.capitals)) map.removeLayer(cityLayers.capitals);
            if (map.hasLayer(cityLayers.megacities)) map.removeLayer(cityLayers.megacities);
        }

        // Large cities: zoom >= 4
        if (zoom >= 4) {
            if (!map.hasLayer(cityLayers.large)) map.addLayer(cityLayers.large);
        } else {
            if (map.hasLayer(cityLayers.large)) map.removeLayer(cityLayers.large);
        }

        // Medium cities: zoom >= 5
        if (zoom >= 5) {
            if (!map.hasLayer(cityLayers.medium)) map.addLayer(cityLayers.medium);
        } else {
            if (map.hasLayer(cityLayers.medium)) map.removeLayer(cityLayers.medium);
        }

        // Small cities: zoom >= 6
        if (zoom >= 6) {
            if (!map.hasLayer(cityLayers.small)) map.addLayer(cityLayers.small);
        } else {
            if (map.hasLayer(cityLayers.small)) map.removeLayer(cityLayers.small);
        }
    }

    map.on("zoomend", updateLayerVisibility);

    // ─── Load data ──────────────────────────────────────────
    async function init() {
        var loading = document.getElementById("loading");
        try {
            var [countriesResp, geojsonResp, citiesResp] = await Promise.all([
                fetch("/api/countries"),
                fetch("/api/geojson/all"),
                fetch("/api/cities"),
            ]);

            var countries = await countriesResp.json();
            var geojsonData = await geojsonResp.json();
            var cities = await citiesResp.json();

            // Index countries by ISO
            countries.forEach(function (c) {
                if (c.iso_a3) countriesData[c.iso_a3] = c;
            });

            // Add GeoJSON layer
            geojsonLayer = L.geoJSON(geojsonData, {
                style: defaultStyle,
                onEachFeature: onEachFeature,
            }).addTo(map);

            // Add city markers to their tier layers
            addCityMarkers(cities);

            // Set initial visibility based on current zoom
            updateLayerVisibility();

        } catch (err) {
            console.error("Error loading map data:", err);
        } finally {
            loading.classList.add("hidden");
            setTimeout(function () { loading.remove(); }, 500);
        }
    }

    init();

})();
