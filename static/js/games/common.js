/* ============================================================
   GeoFreak Games — Common Framework
   Timer, normalization, scoring, continent filtering.
   ============================================================ */

/* ── Text Normalization ─────────────────────────────────────── */
var GeoUtils = {
    /**
     * Normalize a string for fuzzy comparison:
     *  - NFD decompose + strip combining marks (accents)
     *  - Lowercase
     *  - Collapse whitespace, trim
     *  - Strip punctuation except spaces
     */
    normalize: function (s) {
        if (!s) return '';
        return s
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .replace(/[''ʼ]/g, "'")
            .replace(/[^a-z0-9 ']/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    },

    /** Shuffle array in-place (Fisher–Yates) */
    shuffle: function (arr) {
        for (var i = arr.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
        }
        return arr;
    },

    /* ── Continent filtering ───────────────────────────────── */
    filterByContinent: function (countries, continentKey) {
        if (!continentKey || continentKey === 'all') return countries.slice();
        var map = {
            europe : function (c) { return c.continent === 'Europe'; },
            asia   : function (c) { return c.continent === 'Asia'; },
            africa : function (c) { return c.continent === 'Africa'; },
            america: function (c) { return c.continent === 'North America' || c.continent === 'South America'; },
            oceania: function (c) { return c.continent === 'Oceania'; },
        };
        var fn = map[continentKey];
        return fn ? countries.filter(fn) : countries.slice();
    },

    /* ── Country name matching ─────────────────────────────── */
    /**
     * Build a Set of normalised acceptable answers for a country.
     * Includes common name, official name, and hard-coded aliases.
     */
    /** Get the localised display name for a country. */
    getLocalName: function (country) {
        var lang = window.LANG || 'es';
        var key = 'name_' + lang;
        if (country[key]) return country[key];
        if (lang !== 'en' && country.name_es) return country.name_es;
        return country.name;
    },

    /** Get the localised capital name for a country. */
    getLocalCapital: function (country) {
        var lang = window.LANG || 'es';
        var key = 'capital_' + lang;
        if (country[key]) return country[key];
        if (lang !== 'en' && country.capital_es) return country.capital_es;
        return country.capital;
    },

    getCountryNames: function (country) {
        var names = new Set();
        if (country.name) names.add(GeoUtils.normalize(country.name));
        if (country.name_es) names.add(GeoUtils.normalize(country.name_es));
        if (country.name_fr) names.add(GeoUtils.normalize(country.name_fr));
        if (country.name_it) names.add(GeoUtils.normalize(country.name_it));
        if (country.name_ru) names.add(GeoUtils.normalize(country.name_ru));
        if (country.name_official) names.add(GeoUtils.normalize(country.name_official));
        // Aliases
        var aliases = COUNTRY_ALIASES[country.iso_a3];
        if (aliases) {
            aliases.forEach(function (a) { names.add(GeoUtils.normalize(a)); });
        }
        // Try stripping common prefixes for matching
        names.forEach(function (n) {
            ['republic of ', 'the ', 'kingdom of ', 'state of ',
             'federation of ', 'commonwealth of ', 'democratic republic of the ',
             'democratic republic of ', 'people\'s republic of ',
             'united republic of ', 'republica de ', 'republica del ',
             'republica democratica de ', 'republica democratica del ',
             'reino de ', 'estado de ', 'estados '].forEach(function (p) {
                if (n.indexOf(p) === 0) names.add(n.slice(p.length));
            });
        });
        names.delete('');
        return names;
    },

    /**
     * Build a Set of normalised acceptable answers for a capital.
     */
    getCapitalNames: function (country) {
        var names = new Set();
        if (country.capital) names.add(GeoUtils.normalize(country.capital));
        if (country.capital_es) names.add(GeoUtils.normalize(country.capital_es));
        if (country.capital_fr) names.add(GeoUtils.normalize(country.capital_fr));
        if (country.capital_it) names.add(GeoUtils.normalize(country.capital_it));
        if (country.capital_ru) names.add(GeoUtils.normalize(country.capital_ru));
        var aliases = CAPITAL_ALIASES[country.iso_a3];
        if (aliases) {
            aliases.forEach(function (a) { names.add(GeoUtils.normalize(a)); });
        }
        names.delete('');
        return names;
    },

    /** Get ISO_A3 from a GeoJSON feature's properties. */
    getIso3: function (feature) {
        var p = feature.properties || {};
        return p.ISO_A3 || p.iso_a3 || p.ISO_A3_EH || '';
    },

    /** Format a stat value for display (int / float1 / float3 / money). */
    formatValue: function (val, fmt) {
        var locale = window.LANG === 'en' ? 'en-US' : 'es-ES';
        if (fmt === 'int') return Math.round(val).toLocaleString(locale);
        if (fmt === 'float1') return val.toFixed(1);
        if (fmt === 'float3') return val.toFixed(3);
        if (fmt === 'money') {
            if (val >= 1e12) return (val / 1e12).toFixed(1) + 'T $';
            if (val >= 1e9) return (val / 1e9).toFixed(1) + 'B $';
            if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M $';
            return Math.round(val).toLocaleString(locale) + ' $';
        }
        return String(val);
    },
};

/* ── Hard-coded aliases ────────────────────────────────────── */
var COUNTRY_ALIASES = {
    USA: ['usa','us','united states','estados unidos','eeuu','america','eua'],
    GBR: ['uk','united kingdom','gran bretana','reino unido','england','inglaterra','great britain'],
    RUS: ['russia','rusia'],
    CHN: ['china','prc'],
    KOR: ['south korea','corea del sur','corea','korea'],
    PRK: ['north korea','corea del norte'],
    COD: ['dr congo','rdc','democratic republic of congo','congo kinshasa','republica democratica del congo'],
    COG: ['republic of congo','congo brazzaville','congo'],
    CZE: ['czech republic','czechia','chequia','republica checa'],
    CIV: ['ivory coast','cote d ivoire','costa de marfil'],
    ARE: ['uae','eau','emiratos','emiratos arabes unidos'],
    ZAF: ['south africa','sudafrica'],
    NLD: ['netherlands','holland','holanda','paises bajos'],
    MKD: ['north macedonia','macedonia','macedonia del norte'],
    MMR: ['myanmar','burma','birmania'],
    TUR: ['turkey','turkiye','turquia'],
    TWN: ['taiwan','formosa'],
    PSE: ['palestine','palestina'],
    SWZ: ['eswatini','swaziland','suazilandia'],
    ESP: ['spain','espana','reino de espana'],
    FRA: ['france','francia'],
    DEU: ['germany','alemania','deutschland'],
    ITA: ['italy','italia'],
    JPN: ['japan','japon'],
    BRA: ['brazil','brasil'],
    EGY: ['egypt','egipto'],
    SAU: ['saudi arabia','arabia saudita','arabia saudi'],
    IRQ: ['iraq','irak'],
    SYR: ['syria','siria'],
    GRC: ['greece','grecia'],
    POL: ['poland','polonia'],
    ROU: ['romania','rumania'],
    UKR: ['ukraine','ucrania'],
    NOR: ['norway','noruega'],
    SWE: ['sweden','suecia'],
    DNK: ['denmark','dinamarca'],
    FIN: ['finland','finlandia'],
    BEL: ['belgium','belgica'],
    CHE: ['switzerland','suiza'],
    HUN: ['hungary','hungria'],
    HRV: ['croatia','croacia'],
    LTU: ['lithuania','lituania'],
    LVA: ['latvia','letonia'],
    SVK: ['slovakia','eslovaquia'],
    SVN: ['slovenia','eslovenia'],
    CYP: ['cyprus','chipre'],
    ISL: ['iceland','islandia'],
    IRL: ['ireland','irlanda'],
    NZL: ['new zealand','nueva zelanda'],
    THA: ['thailand','tailandia'],
    PHL: ['philippines','filipinas'],
    MYS: ['malaysia','malasia'],
    KHM: ['cambodia','camboya'],
    KAZ: ['kazakhstan','kazajstan'],
    MNG: ['mongolia'],
    AFG: ['afghanistan','afganistan'],
    MAR: ['morocco','marruecos'],
    DZA: ['algeria','argelia'],
    TUN: ['tunisia','tunez'],
    LBY: ['libya','libia'],
    ETH: ['ethiopia','etiopia'],
    CMR: ['cameroon','camerun'],
    GNQ: ['equatorial guinea','guinea ecuatorial'],
    CAF: ['central african republic','republica centroafricana'],
    NGA: ['nigeria'],
    KEN: ['kenya','kenia'],
    DOM: ['dominican republic','republica dominicana'],
    TTO: ['trinidad and tobago','trinidad y tobago'],
    BIH: ['bosnia','bosnia and herzegovina','bosnia herzegovina'],
    SSD: ['south sudan','sudan del sur'],
    MDG: ['madagascar'],
    LUX: ['luxembourg','luxemburgo'],
    BGR: ['bulgaria'],
    SRB: ['serbia'],
    MNE: ['montenegro'],
    ALB: ['albania'],
    EST: ['estonia'],
    BWA: ['botswana','botsuana'],
    RWA: ['rwanda','ruanda'],
    PAN: ['panama'],
    BLZ: ['belize','belice'],
    SUR: ['suriname','surinam'],
    CPV: ['cape verde','cabo verde'],
    SLE: ['sierra leone','sierra leona'],
    MUS: ['mauritius','mauricio'],
    LAO: ['laos'],
    SGP: ['singapore','singapur'],
    LKA: ['sri lanka','ceilan'],
    ZWE: ['zimbabwe','zimbabue'],
    TJK: ['tajikistan','tayikistan'],
    KGZ: ['kyrgyzstan','kirguistan'],
    TKM: ['turkmenistan'],
    UZB: ['uzbekistan'],
    SLV: ['el salvador'],
    GTM: ['guatemala'],
    HND: ['honduras'],
    NIC: ['nicaragua'],
    CRI: ['costa rica'],
    VEN: ['venezuela'],
    COL: ['colombia'],
    PER: ['peru'],
    CHL: ['chile'],
    ECU: ['ecuador'],
    BOL: ['bolivia'],
    PRY: ['paraguay'],
    URY: ['uruguay'],
    ARG: ['argentina'],
    CUB: ['cuba'],
    MEX: ['mexico'],
    CAN: ['canada'],
    AUS: ['australia'],
    IND: ['india'],
    PAK: ['pakistan'],
    BGD: ['bangladesh'],
    NPL: ['nepal'],
    IRN: ['iran'],
    ISR: ['israel'],
    PRT: ['portugal'],
    AUT: ['austria'],
    MLT: ['malta'],
    GEO: ['georgia'],
    ARM: ['armenia'],
    AZE: ['azerbaijan','azerbaiyan'],
    JOR: ['jordan','jordania'],
    LBN: ['lebanon','libano'],
    OMN: ['oman'],
    YEM: ['yemen'],
    BHR: ['bahrain','barein'],
    QAT: ['qatar'],
    KWT: ['kuwait'],
    TLS: ['east timor','timor leste','timor oriental'],
};

var CAPITAL_ALIASES = {
    USA: ['washington','washington d c','washington dc'],
    GBR: ['london','londres'],
    CHN: ['beijing','pekin','peking'],
    JPN: ['tokyo','tokio'],
    KOR: ['seoul','seul'],
    DEU: ['berlin'],
    ITA: ['rome','roma'],
    ESP: ['madrid'],
    FRA: ['paris'],
    BRA: ['brasilia'],
    RUS: ['moscow','moscu'],
    IND: ['new delhi','nueva delhi'],
    EGY: ['cairo','el cairo'],
    TUR: ['ankara'],
    GRC: ['athens','atenas'],
    POL: ['warsaw','varsovia'],
    NLD: ['amsterdam'],
    BEL: ['brussels','bruselas'],
    AUT: ['vienna','viena'],
    CHE: ['bern','berna'],
    PRT: ['lisbon','lisboa'],
    SWE: ['stockholm','estocolmo'],
    NOR: ['oslo'],
    DNK: ['copenhagen','copenhague'],
    FIN: ['helsinki'],
    IRL: ['dublin'],
    CZE: ['prague','praga'],
    ROU: ['bucharest','bucarest'],
    HUN: ['budapest'],
    HRV: ['zagreb'],
    SRB: ['belgrade','belgrado'],
    BGR: ['sofia'],
    UKR: ['kyiv','kiev'],
    ISR: ['jerusalem','jerusalen'],
    MAR: ['rabat'],
    ZAF: ['pretoria'],
    CAN: ['ottawa'],
    MEX: ['mexico city','ciudad de mexico'],
    ARG: ['buenos aires'],
    CHL: ['santiago'],
    COL: ['bogota'],
    PER: ['lima'],
    VEN: ['caracas'],
    CUB: ['havana','la habana'],
    PAN: ['panama city','ciudad de panama'],
    AUS: ['canberra'],
    NZL: ['wellington'],
    THA: ['bangkok'],
    PHL: ['manila'],
    MYS: ['kuala lumpur'],
    IDN: ['jakarta'],
    IRQ: ['baghdad','bagdad'],
    PRK: ['pyongyang'],
    IRN: ['tehran','teheran'],
    AFG: ['kabul'],
    PAK: ['islamabad'],
    BGD: ['dhaka','dacca'],
    LKA: ['colombo','sri jayawardenepura kotte'],
    ETH: ['addis ababa','addis abeba'],
    KEN: ['nairobi'],
    NGA: ['abuja'],
    TZA: ['dodoma'],
};

/* ── Game Controller ───────────────────────────────────────── */
var GeoGame = {
    correct: 0,
    total: 0,
    startTime: null,
    timerInterval: null,
    timeRemaining: 0,
    settings: {},
    _callbacks: {},

    /** Register game callbacks: { onStart(settings) } */
    init: function (callbacks) {
        this._callbacks = callbacks || {};
        // Wire N-selector buttons if present
        document.querySelectorAll('.n-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.n-btn').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                var nInput = document.getElementById('n-value');
                if (nInput) nInput.value = btn.getAttribute('data-n');
            });
        });
    },

    /** Called when user clicks "Comenzar" */
    start: function () {
        var defaults = (GAME_CONFIG && GAME_CONFIG.defaults) ? GAME_CONFIG.defaults : {};
        var s = {
            continent: 'all',
            timeLimit: defaults.time_limit || 600,
            maxItems: defaults.max_items || 0,
            difficulty: 'normal',
        };

        // Read N selector
        var nInput = document.getElementById('n-value');
        if (nInput && nInput.value) {
            s.maxItems = parseInt(nInput.value) || s.maxItems;
        }

        // Calculate time from N × secs_per_item if configured
        if (defaults.secs_per_item && s.maxItems > 0) {
            s.timeLimit = s.maxItems * defaults.secs_per_item;
        }

        // Read difficulty selector
        var diffInput = document.getElementById('diff-value');
        if (diffInput) {
            s.difficulty = diffInput.value || 'normal';
        }

        // Read countdown toggle (can disable timer entirely)
        var countdownEl = document.getElementById('countdown-toggle');
        if (countdownEl && !countdownEl.checked) {
            s.timeLimit = 0;
        }

        this.settings = s;
        this.correct = 0;
        this.total = 0;

        // Hide settings, show HUD + game area
        document.getElementById('settings-overlay').style.display = 'none';
        document.getElementById('game-hud').style.display = 'flex';
        document.getElementById('game-area').style.display = '';

        // Timer — if delayTimer is set, defer until startTimer() is called
        this.timeRemaining = s.timeLimit;
        if (this._callbacks.delayTimer) {
            // Show paused timer display
            if (s.timeLimit > 0) {
                this._updateTimer();
            } else {
                document.getElementById('hud-timer').textContent = '⏱️ ∞';
            }
        } else {
            this._beginTimer();
        }

        if (this._callbacks.onStart) this._callbacks.onStart(s);
    },

    /** Start (or resume) the countdown timer. Called automatically unless delayTimer is set. */
    startTimer: function () {
        this._beginTimer();
    },

    _beginTimer: function () {
        this.startTime = Date.now();
        if (this.settings.timeLimit > 0) {
            this._updateTimer();
            var self = this;
            this.timerInterval = setInterval(function () {
                self.timeRemaining--;
                self._updateTimer();
                if (self.timeRemaining <= 0) {
                    self.endGame();
                }
            }, 1000);
        } else {
            document.getElementById('hud-timer').textContent = '⏱️ ∞';
        }
    },

    _updateTimer: function () {
        var t = Math.max(0, this.timeRemaining);
        var m = Math.floor(t / 60);
        var s = t % 60;
        var display = m + ':' + (s < 10 ? '0' : '') + s;
        var el = document.getElementById('hud-timer');
        el.textContent = '⏱️ ' + display;
        el.className = 'hud-timer' + (t <= 30 ? ' danger' : t <= 120 ? ' warning' : '');
    },

    setTotal: function (n) {
        this.total = n;
        this._updateHudScore();
    },

    addCorrect: function () {
        this.correct++;
        this._updateHudScore();
    },

    _updateHudScore: function () {
        var c = document.getElementById('hud-correct');
        var t = document.getElementById('hud-total');
        if (c) c.textContent = this.correct;
        if (t) t.textContent = this.total;
    },

    endGame: function () {
        if (this.timerInterval) clearInterval(this.timerInterval);
        var elapsedMs = Date.now() - this.startTime;
        var elapsed = Math.round(elapsedMs / 1000);
        var pct = this.total > 0 ? Math.round((this.correct / this.total) * 100) : 0;
        var m = Math.floor(elapsed / 60);
        var s = elapsed % 60;

        // Populate hidden fallback stats (still used as data source)
        document.getElementById('result-correct').textContent = this.correct;
        document.getElementById('result-total').textContent = this.total;
        document.getElementById('result-pct').textContent = pct + '%';
        document.getElementById('result-time').textContent = m + ':' + (s < 10 ? '0' : '') + s;

        document.querySelector('.results-icon').innerHTML = resultIcon(this.correct, this.total);

        // Build enhanced results UI (stars + metrics + share + actions)
        GeoResults.build(this.correct, this.total, elapsedMs);

        document.getElementById('results-overlay').style.display = 'flex';
        this._saveResult(elapsed);
    },

    /** Save match result to backend. Called automatically by endGame. */
    _saveResult: function (elapsedSec) {
        var gameType = GAME_CONFIG && GAME_CONFIG.id ? GAME_CONFIG.id : '';
        if (!gameType) return;
        // ordering, comparison & geostats games save their own results
        if (gameType === 'ordering' || gameType === 'comparison' || gameType === 'geostats') return;

        var payload = {
            game_type: gameType,
            mode: 'solo',
            score: this.correct,
            total: this.total,
            accuracy: this.total > 0 ? this.correct / this.total : 0,
            time_ms: elapsedSec * 1000,
            config: { continent: this.settings.continent || 'all' }
        };
        fetch('/api/matches/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).catch(function () {});
    },

    quit: function () {
        this.endGame();
    },
};

/* ── Difficulty dropdown binding ────────────────────────────── */
(function () {
    var toggle = document.getElementById('diff-toggle');
    var menu = document.getElementById('diff-menu');
    var input = document.getElementById('diff-value');
    var label = document.getElementById('diff-label');
    if (!toggle || !menu) return;

    toggle.addEventListener('click', function (e) {
        e.stopPropagation();
        menu.classList.toggle('open');
    });

    menu.querySelectorAll('li').forEach(function (li) {
        li.addEventListener('click', function (e) {
            e.stopPropagation();
            menu.querySelectorAll('li').forEach(function (l) { l.classList.remove('selected'); });
            li.classList.add('selected');
            input.value = li.getAttribute('data-diff');
            label.textContent = li.textContent;
            menu.classList.remove('open');
        });
    });

    document.addEventListener('click', function () {
        menu.classList.remove('open');
    });
})();

/* ── Tooltip for stat descriptions (shared) ────────────────────── */
var _isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

function dismissTooltip() {
    var existing = document.querySelector('.stat-tooltip-popup');
    if (existing) existing.remove();
}

function toggleTooltip(el) {
    var existing = document.querySelector('.stat-tooltip-popup');
    if (existing) {
        var wasSame = existing._trigger === el;
        existing.remove();
        if (wasSame) return;
    }
    _showTooltip(el);
}

function _showTooltip(el) {
    var text = el.getAttribute('data-tooltip');
    if (!text) return;
    var tip = document.createElement('div');
    tip.className = 'stat-tooltip-popup';
    tip.textContent = text;
    tip._trigger = el;
    var rect = el.getBoundingClientRect();
    tip.style.position = 'fixed';
    tip.style.left = Math.max(8, rect.left + rect.width / 2 - 150) + 'px';
    tip.style.top = (rect.bottom + 8) + 'px';
    document.body.appendChild(tip);
    setTimeout(function() {
        document.addEventListener('click', function handler(e) {
            if (!tip.contains(e.target) && e.target !== el) {
                tip.remove();
                document.removeEventListener('click', handler);
            }
        });
    }, 10);
    return tip;
}

/** Auto-show tooltip briefly when a new question appears, then fade out */
function flashTooltip(el) {
    dismissTooltip();
    var tip = _showTooltip(el);
    if (!tip) return;
    tip.classList.add('flash');
    setTimeout(function () {
        tip.classList.add('fade-out');
        setTimeout(function () { if (tip.parentNode) tip.remove(); }, 500);
    }, 1500);
}

function bindTooltipTrigger(el) {
    if (_isTouch) {
        el.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleTooltip(el);
        });
    } else {
        el.addEventListener('mouseenter', function () { _showTooltip(el); });
        el.addEventListener('mouseleave', function () { dismissTooltip(); });
    }
}

/* ============================================================
   resultIcon — Animated SVG based on score (0–10 scale)
   ============================================================ */
function resultIcon(score, total) {
    var n = total > 0 ? Math.round((score / total) * 10) : 0;
    if (n <= 4) {
        // Rain cloud — gray/blue, swaying cloud + falling drops
        return '<svg width="80" height="80" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">' +
            '<style>' +
            '.ri-cld{animation:ri-sway 2.6s ease-in-out infinite;transform-origin:40px 38px}' +
            '@keyframes ri-sway{0%,100%{transform:rotate(-4deg) translateX(-1px)}50%{transform:rotate(4deg) translateX(1px)}}' +
            '.ri-r1{animation:ri-drop 1.1s 0s linear infinite}' +
            '.ri-r2{animation:ri-drop 1.1s .38s linear infinite}' +
            '.ri-r3{animation:ri-drop 1.1s .76s linear infinite}' +
            '@keyframes ri-drop{0%{opacity:0;transform:translateY(-6px)}25%{opacity:1}80%{opacity:.8;transform:translateY(10px)}100%{opacity:0;transform:translateY(10px)}}' +
            '</style>' +
            '<g class="ri-cld">' +
            '<ellipse cx="28" cy="40" rx="13" ry="11" fill="#94a3b8"/>' +
            '<ellipse cx="40" cy="32" rx="15" ry="13" fill="#94a3b8"/>' +
            '<ellipse cx="52" cy="40" rx="11" ry="9" fill="#94a3b8"/>' +
            '<rect x="16" y="43" width="42" height="12" rx="6" fill="#94a3b8"/>' +
            '</g>' +
            '<g class="ri-r1"><line x1="26" y1="59" x2="23" y2="70" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round"/></g>' +
            '<g class="ri-r2"><line x1="39" y1="59" x2="36" y2="70" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round"/></g>' +
            '<g class="ri-r3"><line x1="52" y1="59" x2="49" y2="70" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round"/></g>' +
            '</svg>';
    }
    if (n <= 6) {
        // Speedometer at ~50% — orange needle swinging
        return '<svg width="80" height="80" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">' +
            '<style>' +
            '.ri-ndl{animation:ri-swing 2s ease-in-out infinite;transform-origin:40px 50px}' +
            '@keyframes ri-swing{0%,100%{transform:rotate(-10deg)}50%{transform:rotate(10deg)}}' +
            '.ri-arc{animation:ri-pulse 2s ease-in-out infinite}' +
            '@keyframes ri-pulse{0%,100%{opacity:1}50%{opacity:.6}}' +
            '</style>' +
            '<circle cx="40" cy="40" r="31" fill="#f8fafc" stroke="#e2e8f0" stroke-width="2"/>' +
            '<path d="M12 52 A28 28 0 0 1 68 52" fill="none" stroke="#e2e8f0" stroke-width="7" stroke-linecap="round"/>' +
            '<path class="ri-arc" d="M12 52 A28 28 0 0 1 40 24" fill="none" stroke="#f97316" stroke-width="7" stroke-linecap="round"/>' +
            '<circle cx="12" cy="52" r="3" fill="#cbd5e1"/>' +
            '<circle cx="68" cy="52" r="3" fill="#cbd5e1"/>' +
            '<circle cx="40" cy="24" r="3" fill="#f97316" opacity=".5"/>' +
            '<g class="ri-ndl"><line x1="40" y1="50" x2="40" y2="27" stroke="#334155" stroke-width="3.5" stroke-linecap="round"/></g>' +
            '<circle cx="40" cy="50" r="5" fill="#334155"/>' +
            '<circle cx="40" cy="50" r="2.5" fill="#94a3b8"/>' +
            '</svg>';
    }
    if (n <= 8) {
        // Checkmark in circle — green, pop-in then glow pulse
        return '<svg width="80" height="80" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">' +
            '<style>' +
            '.ri-ck{animation:ri-pop .55s cubic-bezier(.68,-.55,.27,1.55) both,ri-glow 2.2s .6s ease-in-out infinite}' +
            '@keyframes ri-pop{0%{transform:scale(0);opacity:0}100%{transform:scale(1);opacity:1}}' +
            '@keyframes ri-glow{0%,100%{filter:drop-shadow(0 0 4px #22c55e55)}50%{filter:drop-shadow(0 0 12px #22c55eaa)}}' +
            '</style>' +
            '<g class="ri-ck">' +
            '<circle cx="40" cy="40" r="29" fill="#dcfce7" stroke="#22c55e" stroke-width="3"/>' +
            '<polyline points="25,40 36,53 56,26" fill="none" stroke="#22c55e" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"/>' +
            '</g>' +
            '</svg>';
    }
    if (n === 9) {
        // Shining star — gold, rotate-scale + ray pulse
        return '<svg width="80" height="80" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">' +
            '<style>' +
            '.ri-rays{animation:ri-rpulse 1.6s ease-in-out infinite;transform-origin:40px 40px}' +
            '@keyframes ri-rpulse{0%,100%{opacity:.45;transform:scale(.9) rotate(0deg)}50%{opacity:1;transform:scale(1.08) rotate(15deg)}}' +
            '.ri-star{animation:ri-spulse 1.6s ease-in-out infinite;transform-origin:40px 40px}' +
            '@keyframes ri-spulse{0%,100%{transform:scale(1) rotate(0deg)}50%{transform:scale(1.06) rotate(-8deg)}}' +
            '</style>' +
            '<g class="ri-rays">' +
            '<line x1="40" y1="5" x2="40" y2="15" stroke="#fcd34d" stroke-width="3" stroke-linecap="round"/>' +
            '<line x1="40" y1="65" x2="40" y2="75" stroke="#fcd34d" stroke-width="3" stroke-linecap="round"/>' +
            '<line x1="5" y1="40" x2="15" y2="40" stroke="#fcd34d" stroke-width="3" stroke-linecap="round"/>' +
            '<line x1="65" y1="40" x2="75" y2="40" stroke="#fcd34d" stroke-width="3" stroke-linecap="round"/>' +
            '<line x1="13" y1="13" x2="20" y2="20" stroke="#fcd34d" stroke-width="2.5" stroke-linecap="round"/>' +
            '<line x1="60" y1="60" x2="67" y2="67" stroke="#fcd34d" stroke-width="2.5" stroke-linecap="round"/>' +
            '<line x1="67" y1="13" x2="60" y2="20" stroke="#fcd34d" stroke-width="2.5" stroke-linecap="round"/>' +
            '<line x1="20" y1="60" x2="13" y2="67" stroke="#fcd34d" stroke-width="2.5" stroke-linecap="round"/>' +
            '</g>' +
            '<g class="ri-star">' +
            '<polygon points="40,14 47,31 65,33 52,45 56,63 40,54 24,63 28,45 15,33 33,31" fill="#fbbf24" stroke="#f59e0b" stroke-width="1.5" stroke-linejoin="round"/>' +
            '</g>' +
            '</svg>';
    }
    // n === 10: Crown with sparkling gems
    return '<svg width="80" height="80" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">' +
        '<style>' +
        '.ri-crown{animation:ri-float 2s ease-in-out infinite;transform-origin:40px 44px}' +
        '@keyframes ri-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}' +
        '.ri-sp1{animation:ri-spark 1.8s 0s ease-in-out infinite;transform-origin:16px 22px}' +
        '.ri-sp2{animation:ri-spark 1.8s .6s ease-in-out infinite;transform-origin:64px 18px}' +
        '.ri-sp3{animation:ri-spark 1.8s 1.2s ease-in-out infinite;transform-origin:68px 56px}' +
        '@keyframes ri-spark{0%,100%{opacity:0;transform:scale(0)}35%{opacity:1;transform:scale(1.1)}70%{opacity:1;transform:scale(.9)}85%{opacity:0}}' +
        '.ri-shine{animation:ri-gshine 2s ease-in-out infinite}' +
        '@keyframes ri-gshine{0%,100%{filter:drop-shadow(0 0 4px #fbbf24aa)}50%{filter:drop-shadow(0 0 14px #fbbf24ee)}}' +
        '</style>' +
        '<g class="ri-sp1"><line x1="16" y1="18" x2="16" y2="26" stroke="#fbbf24" stroke-width="2.5" stroke-linecap="round"/><line x1="12" y1="22" x2="20" y2="22" stroke="#fbbf24" stroke-width="2.5" stroke-linecap="round"/></g>' +
        '<g class="ri-sp2"><line x1="64" y1="14" x2="64" y2="22" stroke="#a78bfa" stroke-width="2.5" stroke-linecap="round"/><line x1="60" y1="18" x2="68" y2="18" stroke="#a78bfa" stroke-width="2.5" stroke-linecap="round"/></g>' +
        '<g class="ri-sp3"><line x1="68" y1="52" x2="68" y2="60" stroke="#34d399" stroke-width="2.5" stroke-linecap="round"/><line x1="64" y1="56" x2="72" y2="56" stroke="#34d399" stroke-width="2.5" stroke-linecap="round"/></g>' +
        '<g class="ri-shine ri-crown">' +
        '<path d="M18 52 L18 36 L30 47 L40 22 L50 47 L62 36 L62 52 Z" fill="#fbbf24" stroke="#f59e0b" stroke-width="1.5" stroke-linejoin="round"/>' +
        '<rect x="16" y="52" width="48" height="11" rx="3.5" fill="#f59e0b"/>' +
        '<circle cx="40" cy="57" r="3.5" fill="#ef4444"/>' +
        '<circle cx="28" cy="57" r="2.8" fill="#3b82f6"/>' +
        '<circle cx="52" cy="57" r="2.8" fill="#22c55e"/>' +
        '<circle cx="40" cy="22" r="3" fill="#fef3c7"/>' +
        '</g>' +
        '</svg>';
}

/* ============================================================
   GeoResults — Enhanced results overlay (stars, share, actions)
   Used by ALL games.
   ============================================================ */
var GeoResults = (function () {
    var _halfStarId = 0;
    var _lastResult = null;

    /* ── SVG Stars ────────────────────────────────────────── */
    function starSVG(type) {
        var w = 28, h = 28;
        var pts = '14,3 17.5,10 25,11.5 19.5,17 21,24.5 14,20.5 7,24.5 8.5,17 3,11.5 10.5,10';
        if (type === 'full') {
            return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">' +
                '<polygon points="'+pts+'" fill="#f59e0b" stroke="#f59e0b" stroke-width="1.2" stroke-linejoin="round"/></svg>';
        }
        if (type === 'half') {
            var uid = 'hs' + (++_halfStarId);
            return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">' +
                '<defs><clipPath id="'+uid+'-l"><rect x="0" y="0" width="14" height="28"/></clipPath>' +
                '<clipPath id="'+uid+'-r"><rect x="14" y="0" width="14" height="28"/></clipPath></defs>' +
                '<polygon points="'+pts+'" fill="#f59e0b" stroke="#f59e0b" stroke-width="1.2" stroke-linejoin="round" clip-path="url(#'+uid+'-l)"/>' +
                '<polygon points="'+pts+'" fill="none" stroke="#f59e0b" stroke-width="1.2" stroke-linejoin="round" clip-path="url(#'+uid+'-r)"/></svg>';
        }
        return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">' +
            '<polygon points="'+pts+'" fill="none" stroke="#d1d5db" stroke-width="1.2" stroke-linejoin="round"/></svg>';
    }

    function renderStarsHTML(score, total) {
        var stars = total > 0 ? (score / total) * 5 : 0;
        var full = Math.floor(stars);
        var half = (stars - full) >= 0.5 ? 1 : 0;
        var empty = 5 - full - half;
        var html = '<div class="daily-stars">';
        for (var i = 0; i < full; i++) html += starSVG('full');
        if (half) html += starSVG('half');
        for (var j = 0; j < empty; j++) html += starSVG('empty');
        html += '</div>';
        return html;
    }

    function starsText(score, total) {
        var stars = total > 0 ? (score / total) * 5 : 0;
        var full = Math.floor(stars);
        var half = (stars - full) >= 0.5 ? 1 : 0;
        var empty = 5 - full - half;
        var txt = '';
        for (var i = 0; i < full; i++) txt += '★';
        if (half) txt += '⯨';
        for (var j = 0; j < empty; j++) txt += '☆';
        return txt;
    }

    function fmtTime(ms) {
        var sec = Math.round(ms / 1000);
        var m = Math.floor(sec / 60);
        var s = sec % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    /* ── Build enhanced results ───────────────────────────── */
    function build(score, total, timeMs) {
        _lastResult = { score: score, total: total, timeMs: timeMs };

        // Hide normal stats grid, show enhanced section
        var normalStats = document.getElementById('results-stats-normal');
        if (normalStats) normalStats.style.display = 'none';

        var section = document.getElementById('results-enhanced');
        section.style.display = '';
        section.innerHTML =
            renderStarsHTML(score, total) +
            '<div class="daily-metrics">' +
                '<div class="daily-metric">' +
                    '<span class="daily-metric-value">' + score + '/' + total + '</span>' +
                    '<span class="daily-metric-label">' + (T['daily.hits'] || 'Correct') + '</span>' +
                '</div>' +
                '<div class="daily-metric">' +
                    '<span class="daily-metric-value">' + fmtTime(timeMs) + '</span>' +
                    '<span class="daily-metric-label">' + (T['game.time'] || 'Time') + '</span>' +
                '</div>' +
            '</div>';

        // Build actions
        var actions = document.getElementById('results-actions');
        actions.className = 'results-actions daily-actions';
        var html = '';

        // Share row — copy button only on touch/mobile (navigator.share available)
        html += '<div class="daily-share-row">' +
            '<button class="btn-daily-share" onclick="GeoResults.share()">' +
                '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg> ' +
                (T['daily.share'] || 'Share results') +
            '</button>' +
            (navigator.share
                ? '<button class="btn-daily-copy" id="btn-geo-copy" onclick="GeoResults.copy()">' +
                    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> ' +
                    (T['daily.copy'] || 'Copy') +
                  '</button>'
                : '') +
            '</div>';

        // Play again + Other games
        html += '<button class="btn btn-primary results-replay-btn" onclick="location.reload()">' +
            (T['game.replay'] || 'Play again') + '</button>';
        html += '<a href="/games" class="daily-other-games">' +
            (T['game.others'] || 'Other games') + '</a>';

        // Auth-dependent: register prompt or quiet stats link
        if (typeof IS_LOGGED_IN !== 'undefined' && !IS_LOGGED_IN) {
            html += '<div class="daily-register-block">' +
                '<a href="/register" class="btn-daily-register">' +
                    (T['daily.register_btn'] || 'Sign up') +
                '</a>' +
                '<p class="daily-register-hint">' +
                    (T['daily.register_prompt'] || 'Register to save your progress!') +
                '</p></div>';
        } else if (typeof IS_LOGGED_IN !== 'undefined' && IS_LOGGED_IN) {
            html += '<a href="/profile#stats" class="btn-results-stats">' +
                (T['game.view_stats'] || 'Ver mis estadísticas') +
                '</a>';
        }

        actions.innerHTML = html;
    }

    /* ── Build daily-specific results (extends build) ─────── */
    function buildDaily(score, total, timeMs, opts) {
        build(score, total, timeMs);

        var actions = document.getElementById('results-actions');
        // Remove replay button for daily
        var replayBtn = actions.querySelector('.btn.btn-primary');
        if (replayBtn) replayBtn.remove();

        // Add countdown before the "other games" link
        var otherLink = actions.querySelector('.daily-other-games');
        var countdownWrap = document.createElement('div');
        countdownWrap.className = 'daily-countdown-wrap';
        countdownWrap.innerHTML = '<p class="daily-countdown" id="daily-countdown"></p>';
        if (otherLink) {
            actions.insertBefore(countdownWrap, otherLink);
        } else {
            actions.appendChild(countdownWrap);
        }

        // For anon users: remove stats link, ensure register block exists
        if (opts && opts.isAnon) {
            var registerBlock = actions.querySelector('.daily-register-block');
            if (!registerBlock) {
                var regHtml = '<div class="daily-register-block">' +
                    '<a href="/register" class="btn-daily-register">' +
                        (T['daily.register_btn'] || 'Sign up') +
                    '</a>' +
                    '<p class="daily-register-hint">' +
                        (T['daily.register_prompt'] || 'Register to save your progress!') +
                    '</p></div>';
                actions.insertAdjacentHTML('beforeend', regHtml);
            }
        } else {
            // Logged-in: replace register block with stats link
            var regBlock = actions.querySelector('.daily-register-block');
            if (regBlock) regBlock.remove();
            var statsLink = document.createElement('a');
            statsLink.href = '/profile';
            statsLink.className = 'btn-daily-stats';
            statsLink.textContent = T['daily.view_stats'] || '📊 View my stats';
            var otherGames = actions.querySelector('.daily-other-games');
            if (otherGames) {
                actions.insertBefore(statsLink, otherGames);
            } else {
                actions.appendChild(statsLink);
            }
        }
    }

    /* ── Share / Copy ─────────────────────────────────────── */
    function getShareText() {
        if (!_lastResult) return '';
        var r = _lastResult;
        var isDaily = GAME_CONFIG && GAME_CONFIG.daily;
        var gameName = (GAME_CONFIG && GAME_CONFIG.name) || 'GeoFreak';
        var template = isDaily
            ? (T['daily.share_text'] || 'I got {score}/{total} on today\'s GeoFreak daily challenge')
            : (T['game.share_text'] || 'I got {score}/{total} on GeoFreak — {game}');
        var text = template.replace('{score}', r.score).replace('{total}', r.total).replace('{game}', gameName);
        text += '\n' + starsText(r.score, r.total);
        text += '\n⏱️ ' + fmtTime(r.timeMs);
        if (isDaily) {
            text += '\nhttps://geofreak.net/games/daily';
        } else {
            text += '\nhttps://geofreak.net/games';
        }
        return text;
    }

    function share() {
        var text = getShareText();
        var isDaily = GAME_CONFIG && GAME_CONFIG.daily;
        var title = isDaily
            ? (T['daily.share_title'] || '🌍 GeoFreak — Daily Challenge')
            : (T['game.share_title'] || '🌍 GeoFreak');
        if (navigator.share) {
            navigator.share({ title: title, text: text }).catch(function () {});
        } else {
            copy();
        }
    }

    function copy() {
        var text = getShareText();
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                var btn = document.getElementById('btn-geo-copy');
                if (btn) {
                    btn.textContent = T['daily.copied'] || '¡Copiado!';
                    setTimeout(function () {
                        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> ' + (T['daily.copy'] || 'Copy');
                    }, 2000);
                }
            });
        }
    }

    return { build: build, buildDaily: buildDaily, share: share, copy: copy, starsText: starsText, fmtTime: fmtTime };
})();

/* ============================================================
   GeoReview — Post-game question review navigation
   After closing the results modal, the player can navigate
   through all answered questions using ← → arrows.
   ============================================================ */
var GeoReview = (function () {
    var _snapshots = [];
    var _reviewIdx = -1;
    var _active = false;
    var _nav = null;

    /** Capture the current #game-area state as a reviewable snapshot. */
    function snapshot() {
        var area = document.getElementById('game-area');
        if (!area) return;
        var clone = area.cloneNode(true);
        // Convert canvases to static images so they survive innerHTML restore
        var origCanvases = area.querySelectorAll('canvas');
        var cloneCanvases = clone.querySelectorAll('canvas');
        for (var i = 0; i < origCanvases.length; i++) {
            try {
                var img = document.createElement('img');
                img.src = origCanvases[i].toDataURL();
                img.style.width = '100%';
                img.style.maxHeight = (origCanvases[i].parentElement
                    ? origCanvases[i].parentElement.clientHeight : 300) + 'px';
                img.className = origCanvases[i].className;
                cloneCanvases[i].parentNode.replaceChild(img, cloneCanvases[i]);
            } catch (e) { /* cross-origin canvas — skip */ }
        }
        _snapshots.push(clone.innerHTML);
    }

    /** Activate review mode — called when the results overlay is dismissed. */
    function activate() {
        if (_snapshots.length === 0) return;
        _active = true;
        _reviewIdx = _snapshots.length - 1;
        _showNav();
        _updateNav();
        _restoreSnapshot();
    }

    function deactivate() {
        _active = false;
        _hideNav();
    }

    function isActive() { return _active; }

    /** Navigate by delta (-1 = prev, +1 = next). */
    function navigate(delta) {
        if (!_active) return;
        var newIdx = _reviewIdx + delta;
        if (newIdx < 0) return;
        if (newIdx >= _snapshots.length) {
            // Past the last question → re-open results
            showResults();
            return;
        }
        _reviewIdx = newIdx;
        _restoreSnapshot();
        _updateNav();
    }

    function _restoreSnapshot() {
        var area = document.getElementById('game-area');
        if (area) area.innerHTML = _snapshots[_reviewIdx];
    }

    function _showNav() {
        if (_nav) { _nav.style.display = 'flex'; return; }
        _nav = document.createElement('div');
        _nav.className = 'review-nav';
        _nav.id = 'review-nav';
        _nav.innerHTML =
            '<button class="review-nav-arrow" id="review-prev" onclick="GeoReview.navigate(-1)">&#8249;</button>' +
            '<span class="review-nav-counter" id="review-counter"></span>' +
            '<button class="review-nav-arrow" id="review-next" onclick="GeoReview.navigate(1)">&#8250;</button>' +
            '<button class="review-nav-results" onclick="GeoReview.showResults()">' +
                (T['review.results'] || '📊') +
            '</button>';
        document.body.appendChild(_nav);
    }

    function _hideNav() {
        if (_nav) _nav.style.display = 'none';
    }

    function _updateNav() {
        var counter = document.getElementById('review-counter');
        if (counter) counter.textContent = (_reviewIdx + 1) + ' / ' + _snapshots.length;
        var prev = document.getElementById('review-prev');
        if (prev) prev.disabled = (_reviewIdx <= 0);
    }

    /** Re-open the results overlay and exit review mode. */
    function showResults() {
        document.getElementById('results-overlay').style.display = 'flex';
        deactivate();
    }

    /** Reset all state (for a new game / page reload). */
    function reset() {
        _snapshots = [];
        _reviewIdx = -1;
        _active = false;
        if (_nav) { _nav.remove(); _nav = null; }
    }

    return {
        snapshot: snapshot,
        activate: activate,
        deactivate: deactivate,
        isActive: isActive,
        navigate: navigate,
        showResults: showResults,
        reset: reset
    };
})();

/* ── Keyboard: Escape to toggle results, Arrows to review ── */
document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
        if (GeoReview.isActive()) {
            GeoReview.showResults();
        } else {
            var overlay = document.getElementById('results-overlay');
            if (overlay && overlay.style.display !== 'none') {
                overlay.style.display = 'none';
                GeoReview.activate();
            }
        }
    }
    if (GeoReview.isActive()) {
        if (e.key === 'ArrowLeft')  { e.preventDefault(); GeoReview.navigate(-1); }
        if (e.key === 'ArrowRight') { e.preventDefault(); GeoReview.navigate(1); }
    }
});
