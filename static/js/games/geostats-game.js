/* ============================================================
   GeoFreak — GeoStats Game
   Guess which country is marked on a stat distribution curve.
   ============================================================ */

var GeoStatsGame = (function () {
    var questions = [];
    var countriesLookup = {};
    var maxAttempts = 5;
    var currentIdx = 0;
    var currentAttempts = 0;
    var guessedIsos = {};
    var chart = null;
    var totalScore = 0;
    var resolved = false;

    /* ── Name → ISO reverse map ──────────────────────────── */
    var nameToIso = null;

    function buildNameMap() {
        nameToIso = {};
        for (var iso in countriesLookup) {
            var c = countriesLookup[iso];
            c.iso_a3 = iso; // GeoUtils.getCountryNames expects this
            var names = GeoUtils.getCountryNames(c);
            names.forEach(function (n) {
                if (!nameToIso[n]) nameToIso[n] = iso;
            });
        }
    }

    function resolveInput(text) {
        if (!nameToIso) buildNameMap();
        var norm = GeoUtils.normalize(text);
        return nameToIso[norm] || null;
    }

    function getDisplayName(iso) {
        var c = countriesLookup[iso];
        if (!c) return iso;
        var lang = window.LANG || 'es';
        if (lang === 'es' && c.name_es) return c.name_es;
        if (lang === 'fr' && c.name_fr) return c.name_fr;
        if (lang === 'it' && c.name_it) return c.name_it;
        if (lang === 'ru' && c.name_ru) return c.name_ru;
        return c.name || iso;
    }

    /* ── Init ────────────────────────────────────────────── */

    function init() {
        GeoGame.init({ onStart: loadData });
    }
    init();

    function loadData(settings) {
        var num = settings.maxItems || 10;
        var continent = settings.continent || 'all';
        var defaults = (GAME_CONFIG && GAME_CONFIG.defaults) ? GAME_CONFIG.defaults : {};
        maxAttempts = defaults.max_attempts || 5;

        fetch('/api/quiz/geostats?num=' + num + '&continent=' + continent)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                questions = data.questions || [];
                countriesLookup = data.countries_lookup || {};
                if (data.max_attempts) maxAttempts = data.max_attempts;
                currentIdx = 0;
                totalScore = 0;
                GeoGame.setTotal(questions.length);
                buildNameMap();
                showQuestion();
            });
    }

    /* ── Show question ───────────────────────────────────── */

    function showQuestion() {
        if (currentIdx >= questions.length) {
            saveResult();
            GeoGame.endGame();
            return;
        }
        var q = questions[currentIdx];
        currentAttempts = 0;
        guessedIsos = {};
        resolved = false;

        document.getElementById('q-current').textContent = currentIdx + 1;
        document.getElementById('q-total').textContent = questions.length;

        // Prompt
        var labelKey = T['stat.label_key'] || 'label_es';
        var descKey = labelKey.replace('label_', 'description_');
        var statLabel = q.stat_info[labelKey].toLowerCase();
        var statDesc = q.stat_info[descKey] || '';

        var promptEl = document.getElementById('geostats-prompt');
        promptEl.innerHTML = (T['gs.prompt'] || '').replace('{stat}', statLabel);

        if (statDesc) {
            var em = promptEl.querySelector('em');
            if (em) {
                em.classList.add('stat-tooltip-trigger');
                em.setAttribute('data-tooltip', statDesc);
                bindTooltipTrigger(em);
                flashTooltip(em);
            }
        }

        updateStatus();
        renderChart(q);

        // Reset input
        var input = document.getElementById('geostats-input');
        input.value = '';
        input.disabled = false;
        input.focus();
        document.getElementById('btn-guess').disabled = false;
        document.getElementById('btn-guess').style.display = '';
        document.getElementById('btn-gs-next').style.display = 'none';
        clearFeedback();
    }

    /* ── Chart ───────────────────────────────────────────── */

    function renderChart(q) {
        if (chart) { chart.destroy(); chart = null; }

        var canvas = document.getElementById('geostats-chart');
        var ctx = canvas.getContext('2d');
        var h = canvas.parentElement.clientHeight || 300;
        var gradient = ctx.createLinearGradient(0, 0, 0, h);
        gradient.addColorStop(0, 'rgba(26, 115, 232, 0.22)');
        gradient.addColorStop(1, 'rgba(26, 115, 232, 0.01)');

        var labels = q.curve.map(function (_, i) { return i; });

        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: q.curve,
                    borderColor: '#1a73e8',
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.35,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                    borderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 500 },
                interaction: { mode: 'nearest', intersect: false },
                scales: {
                    x: {
                        display: true,
                        grid: { display: false },
                        ticks: { display: false },
                        border: { display: true, color: 'rgba(0,0,0,0.08)' }
                    },
                    y: {
                        display: true,
                        grid: { color: 'rgba(0,0,0,0.04)' },
                        border: { display: false },
                        ticks: {
                            callback: function (val) {
                                return GeoUtils.formatValue(val, q.stat_info.format);
                            },
                            maxTicksLimit: 6,
                            font: { size: 11 },
                            color: '#94a3b8'
                        }
                    }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false },
                    zoom: {
                        pan: { enabled: true, mode: 'x' },
                        zoom: {
                            wheel: { enabled: true },
                            pinch: { enabled: true },
                            mode: 'x',
                        }
                    },
                    annotation: {
                        annotations: {
                            targetLine: {
                                type: 'line',
                                xMin: q.target_index,
                                xMax: q.target_index,
                                borderColor: '#1a73e8',
                                borderWidth: 2.5,
                                borderDash: [8, 4],
                                label: {
                                    display: true,
                                    content: '❓',
                                    position: 'start',
                                    backgroundColor: '#1a73e8',
                                    color: '#fff',
                                    font: { weight: 'bold', size: 14 },
                                    padding: 6,
                                    borderRadius: 4,
                                }
                            }
                        }
                    }
                }
            }
        });
    }

    /* ── Guess ───────────────────────────────────────────── */

    function guess() {
        if (resolved) return;
        var input = document.getElementById('geostats-input');
        var text = input.value.trim();
        if (!text) return;

        var q = questions[currentIdx];
        var iso = resolveInput(text);

        if (!iso) {
            showFeedback('warning', T['gs.not_found'] || 'Country not recognized');
            input.value = '';
            return;
        }
        if (guessedIsos[iso]) {
            showFeedback('warning', T['gs.already'] || 'Already guessed');
            input.value = '';
            return;
        }
        if (!(iso in q.positions)) {
            var cName = getDisplayName(iso);
            showFeedback('warning', (T['gs.no_data'] || 'No data for {name}').replace('{name}', cName));
            input.value = '';
            return;
        }

        guessedIsos[iso] = true;
        currentAttempts++;

        if (iso === q.target_iso) {
            onCorrect(q);
        } else {
            onWrong(q, iso);
        }
        updateStatus();
        input.value = '';
    }

    function onCorrect(q) {
        var score = computeScore(currentAttempts);
        totalScore += score;
        GeoGame.addCorrect();

        var iso = q.target_iso;
        var cName = getDisplayName(iso);
        var cFlag = (countriesLookup[iso] || {}).flag_emoji || '';

        // Update chart: solid green line with name
        var ann = chart.options.plugins.annotation.annotations;
        ann.targetLine.borderDash = [];
        ann.targetLine.borderColor = '#4caf50';
        ann.targetLine.label.content = cFlag + ' ' + cName;
        ann.targetLine.label.backgroundColor = '#4caf50';
        chart.update();

        var msg = (T['gs.correct'] || '✅ Correct!') +
            '  —  ' + (T['gs.score'] || 'Score') + ': ' + score + '/10';
        showFeedback('correct', msg);
        endQuestion();
    }

    function onWrong(q, iso) {
        var guessIndex = q.positions[iso];
        var cName = getDisplayName(iso);
        var cFlag = (countriesLookup[iso] || {}).flag_emoji || '';

        // Add red line
        var ann = chart.options.plugins.annotation.annotations;
        ann['guess_' + currentAttempts] = {
            type: 'line',
            xMin: guessIndex,
            xMax: guessIndex,
            borderColor: '#ef5350',
            borderWidth: 2,
            label: {
                display: true,
                content: cFlag + ' ' + cName,
                position: 'end',
                backgroundColor: 'rgba(239, 83, 80, 0.9)',
                color: '#fff',
                font: { size: 11 },
                padding: 4,
                borderRadius: 4,
            }
        };
        chart.update();

        if (currentAttempts >= maxAttempts) {
            // Reveal answer
            var tName = getDisplayName(q.target_iso);
            var tFlag = (countriesLookup[q.target_iso] || {}).flag_emoji || '';
            ann.targetLine.label.content = tFlag + ' ' + tName;
            ann.targetLine.borderDash = [];
            chart.update();

            var msg = (T['gs.answer'] || 'The answer was: {name}')
                .replace('{name}', tFlag + ' ' + tName) +
                '  —  ' + (T['gs.score'] || 'Score') + ': 0/10';
            showFeedback('wrong', msg);
            endQuestion();
        } else {
            showFeedback('wrong', T['gs.wrong'] || '❌ Wrong');
            document.getElementById('geostats-input').focus();
        }
    }

    function computeScore(attempts) {
        // 1→10, 2→8, 3→6, 4→4, 5→2
        return Math.max(0, 10 - (attempts - 1) * 2);
    }

    function endQuestion() {
        resolved = true;
        document.getElementById('geostats-input').disabled = true;
        document.getElementById('btn-guess').style.display = 'none';
        document.getElementById('btn-gs-next').style.display = '';
    }

    function next() {
        currentIdx++;
        showQuestion();
    }

    /* ── Status dots ─────────────────────────────────────── */

    function updateStatus() {
        var el = document.getElementById('geostats-status');
        var dots = '';
        for (var i = 0; i < maxAttempts; i++) {
            if (i < currentAttempts) {
                dots += '<span class="attempt-dot used"></span>';
            } else {
                dots += '<span class="attempt-dot"></span>';
            }
        }
        el.innerHTML = dots;
    }

    /* ── Feedback ────────────────────────────────────────── */

    function showFeedback(cls, text) {
        var el = document.getElementById('geostats-feedback');
        el.className = 'geostats-feedback ' + cls;
        el.textContent = text;
    }
    function clearFeedback() {
        var el = document.getElementById('geostats-feedback');
        el.className = 'geostats-feedback';
        el.textContent = '';
    }

    /* ── Save result ─────────────────────────────────────── */

    function saveResult() {
        var elapsed = Date.now() - GeoGame.startTime;
        var avgScore = questions.length > 0 ? totalScore / questions.length : 0;
        var payload = {
            game_type: 'geostats',
            mode: 'solo',
            score: GeoGame.correct,
            total: GeoGame.total,
            accuracy: GeoGame.total > 0 ? GeoGame.correct / GeoGame.total : 0,
            time_ms: elapsed,
            config: {
                continent: GeoGame.settings.continent,
                questions: questions.length,
                avg_score: Math.round(avgScore * 10) / 10
            }
        };
        fetch('/api/matches/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).catch(function () {});
    }

    return { guess: guess, next: next };
})();

/* ── Bind Enter key on input ─────────────────────────────── */
(function () {
    var input = document.getElementById('geostats-input');
    if (input) {
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                GeoStatsGame.guess();
            }
        });
    }
})();
