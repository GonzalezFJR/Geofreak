/* ============================================================
   GeoFreak — Ordering Game
   Player must sort 5 countries by a given statistic.
   ============================================================ */

var OrderingGame = (function () {
    var questions = [];
    var currentIdx = 0;
    var dragSrcEl = null;
    var totalScore = 0;

    function init() {
        GeoGame.init({ onStart: loadData });
    }
    init();

    function _dailyTodayKey() {
        var d = new Date();
        var m = d.getUTCMonth() + 1;
        var day = d.getUTCDate();
        return 'gf_daily_' + d.getUTCFullYear() + '-' + (m < 10 ? '0' + m : m) + '-' + (day < 10 ? '0' + day : day);
    }
    function _getDailyCache() {
        var key = _dailyTodayKey();
        var r = null;
        try { r = JSON.parse(localStorage.getItem(key)); } catch (e) {}
        if (!r || typeof r.score === 'undefined') {
            try {
                var cm = document.cookie.match(/(?:^|;)\s*gf_daily=([^;]*)/);
                if (cm) {
                    var parsed = JSON.parse(decodeURIComponent(cm[1]));
                    if (parsed && parsed.date === key) r = parsed;
                }
            } catch (e) {}
        }
        return (r && typeof r.score !== 'undefined') ? r : null;
    }
    function _setDailyCache(score, total, timeMs) {
        var key = _dailyTodayKey();
        var data = JSON.stringify({ score: score, total: total, time_ms: timeMs });
        try { localStorage.setItem(key, data); } catch (e) {}
        try {
            var cookieData = JSON.stringify({ score: score, total: total, time_ms: timeMs, date: key });
            var exp = new Date(); exp.setDate(exp.getDate() + 2);
            document.cookie = 'gf_daily=' + encodeURIComponent(cookieData) + '; expires=' + exp.toUTCString() + '; path=/; SameSite=Lax';
        } catch (e) {}
    }

    function loadData(settings) {
        var isDaily = GAME_CONFIG && GAME_CONFIG.daily;
        if (isDaily) {
            var loggedIn = typeof IS_LOGGED_IN !== 'undefined' && IS_LOGGED_IN;
            if (!loggedIn) {
                var cached = _getDailyCache();
                if (cached) { showAlreadyPlayed(cached); return; }
            }
            fetch('/api/daily-challenge')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.already_played) {
                        showAlreadyPlayed(data.result);
                        return;
                    }
                    try { localStorage.removeItem(_dailyTodayKey()); } catch (e) {}
                    questions = data.questions || [];
                    currentIdx = 0;
                    totalScore = 0;
                    GeoGame.setTotal(questions.length);
                    GeoGame.beginPlay();
                    showQuestion();
                });
        } else {
            var num = settings.maxItems || 10;
            var difficulty = settings.difficulty || 'normal';
            var cust = (typeof GeoCustomize !== 'undefined') ? GeoCustomize.getState() : {};
            var continent = (cust.dataset === 'countries') ? (cust.continent || settings.continent || 'all') : 'all';
            var extraParams = (typeof GeoCustomize !== 'undefined') ? GeoCustomize.buildApiParams() : '';
            fetch('/api/quiz/ordering?num=' + num + '&continent=' + continent + '&difficulty=' + difficulty + extraParams)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    questions = data.questions || [];
                    currentIdx = 0;
                    totalScore = 0;
                    GeoGame.setTotal(questions.length);
                    GeoGame.beginPlay();
                    showQuestion();
                });
        }
    }

    function showAlreadyPlayed(result) {
        document.getElementById('settings-overlay').style.display = 'none';
        document.getElementById('game-area').style.display = 'none';
        document.getElementById('game-hud').style.display = 'none';
        document.querySelector('.results-icon').innerHTML = resultIcon(result.score, result.total);
        document.getElementById('results-overlay').style.display = 'flex';
        GeoResults.buildDaily(result.score, result.total, result.time_ms, { isAnon: false });
        startCountdown();
    }

    function startCountdown() {
        var el = document.getElementById('daily-countdown');
        if (!el) return;
        function update() {
            var now = new Date();
            var tomorrow = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
            var diff = tomorrow - now;
            var h = Math.floor(diff / 3600000);
            var m = Math.floor((diff % 3600000) / 60000);
            var s = Math.floor((diff % 60000) / 1000);
            el.textContent = (T['daily.next_in'] || 'Next challenge in') + ' ' +
                (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
        }
        update();
        setInterval(update, 1000);
    }

    function showQuestion() {
        if (currentIdx >= questions.length) {
            // Calculate normalized score (average of 0-10 per question)
            var avgScore = questions.length > 0 ? totalScore / questions.length : 0;
            avgScore = Math.round(avgScore * 10) / 10; // 1 decimal
            GeoGame.setNormalizedScore(avgScore);
            saveResult();
            GeoGame.endGame();
            return;
        }
        var q = questions[currentIdx];
        document.getElementById('q-current').textContent = currentIdx + 1;
        document.getElementById('q-total').textContent = questions.length;

        var labelKey = T['stat.label_key'] || 'label_es';
        var descKey = labelKey.replace('label_', 'description_');
        var statLabel = q.stat_info[labelKey].toLowerCase();
        var statDesc = q.stat_info[descKey] || '';

        var direction = q.ascending
            ? (T['ord.prompt_asc'] || 'Sort by <em>{stat}</em> ↑').replace('{stat}', statLabel)
            : (T['ord.prompt_desc'] || 'Sort by <em>{stat}</em> ↓').replace('{stat}', statLabel);

        var promptEl = document.getElementById('ordering-prompt');
        promptEl.innerHTML = direction;

        // Add description tooltip to stat name in prompt
        if (statDesc) {
            var em = promptEl.querySelector('em');
            if (em) {
                em.classList.add('stat-tooltip-trigger');
                em.setAttribute('data-tooltip', statDesc);
                bindTooltipTrigger(em);
            }
        }

        renderItems(q.countries);
        clearFeedback();
        document.getElementById('btn-confirm').disabled = false;
        document.getElementById('btn-confirm').style.display = '';
        var nextBtn = document.getElementById('btn-next');
        if (nextBtn) nextBtn.style.display = 'none';
    }

    function renderItems(countries) {
        var container = document.getElementById('ordering-items');
        container.innerHTML = '';
        countries.forEach(function (c, i) {
            var el = document.createElement('div');
            el.className = 'ordering-item';
            el.setAttribute('draggable', 'true');
            el.setAttribute('data-iso', c.iso_a3);
            el.innerHTML =
                '<span class="ordering-rank">' + (i + 1) + '</span>' +
                '<span class="ordering-handle">☰</span>' +
                '<span class="ordering-flag">' + (c.flag_emoji || '🏳️') + '</span>' +
                '<span class="ordering-name">' + GeoUtils.getLocalName(c) + '</span>';

            // Drag events
            el.addEventListener('dragstart', handleDragStart);
            el.addEventListener('dragover', handleDragOver);
            el.addEventListener('drop', handleDrop);
            el.addEventListener('dragend', handleDragEnd);

            // Touch support
            el.addEventListener('touchstart', handleTouchStart, { passive: false });
            el.addEventListener('touchmove', handleTouchMove, { passive: false });
            el.addEventListener('touchend', handleTouchEnd);

            container.appendChild(el);
        });
    }

    // ── Drag & Drop ─────────────────────────────────────────

    function handleDragStart(e) {
        dragSrcEl = this;
        this.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');
    }

    function handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        var target = closestItem(e.target);
        if (target && target !== dragSrcEl) {
            var container = document.getElementById('ordering-items');
            var items = Array.from(container.children);
            var srcIdx = items.indexOf(dragSrcEl);
            var tgtIdx = items.indexOf(target);
            if (srcIdx < tgtIdx) {
                container.insertBefore(dragSrcEl, target.nextSibling);
            } else {
                container.insertBefore(dragSrcEl, target);
            }
        }
    }

    function handleDrop(e) {
        e.preventDefault();
    }

    function handleDragEnd() {
        this.classList.remove('dragging');
        dragSrcEl = null;
        updateRanks();
    }

    function closestItem(el) {
        while (el && !el.classList.contains('ordering-item')) {
            el = el.parentElement;
        }
        return el;
    }

    // ── Touch support for mobile ────────────────────────────

    var touchItem = null;
    var touchClone = null;

    function handleTouchStart(e) {
        touchItem = this;
        touchItem.classList.add('dragging');
        e.preventDefault();
    }

    function handleTouchMove(e) {
        if (!touchItem) return;
        e.preventDefault();
        var touch = e.touches[0];
        var target = document.elementFromPoint(touch.clientX, touch.clientY);
        var item = closestItem(target);
        if (item && item !== touchItem) {
            var container = document.getElementById('ordering-items');
            var items = Array.from(container.children);
            var srcIdx = items.indexOf(touchItem);
            var tgtIdx = items.indexOf(item);
            if (srcIdx < tgtIdx) {
                container.insertBefore(touchItem, item.nextSibling);
            } else {
                container.insertBefore(touchItem, item);
            }
        }
    }

    function handleTouchEnd() {
        if (touchItem) {
            touchItem.classList.remove('dragging');
            touchItem = null;
            updateRanks();
        }
    }

    function updateRanks() {
        var items = document.querySelectorAll('#ordering-items .ordering-item');
        items.forEach(function (el, i) {
            var rank = el.querySelector('.ordering-rank');
            if (rank) rank.textContent = i + 1;
        });
    }

    // ── Scoring: 0–10 using normalised Kendall tau distance ──

    function computeScore(playerOrder, correctOrder) {
        var n = correctOrder.length;
        if (n <= 1) return 10;
        // Count discordant pairs (Kendall tau distance)
        var posMap = {};
        playerOrder.forEach(function (iso, i) { posMap[iso] = i; });
        var discordant = 0;
        var maxDiscordant = n * (n - 1) / 2;
        for (var i = 0; i < n; i++) {
            for (var j = i + 1; j < n; j++) {
                if (posMap[correctOrder[i]] > posMap[correctOrder[j]]) {
                    discordant++;
                }
            }
        }
        // 0 discordant → 10, all discordant → 0
        return Math.round((1 - discordant / maxDiscordant) * 10 * 10) / 10;
    }

    // ── Confirm answer ──────────────────────────────────────

    function confirm() {
        var container = document.getElementById('ordering-items');
        var items = container.querySelectorAll('.ordering-item');
        var playerOrder = Array.from(items).map(function (el) {
            return el.getAttribute('data-iso');
        });

        var q = questions[currentIdx];
        var correct = q.correct_order;
        var score = computeScore(playerOrder, correct);
        totalScore += score;

        var isCorrect = score === 10;

        // Show correct/incorrect per item + correct ranking number
        items.forEach(function (el, i) {
            var iso = el.getAttribute('data-iso');
            var correctIdx = correct.indexOf(iso);
            var val = q.correct_values[iso];
            var formatted = GeoUtils.formatValue(val, q.stat_info.format);

            var badge = document.createElement('span');
            badge.className = 'ordering-value';
            badge.textContent = formatted;
            el.appendChild(badge);

            // Show the correct position
            var rank = el.querySelector('.ordering-rank');
            if (rank) {
                rank.textContent = correctIdx + 1;
                rank.classList.add(iso === correct[i] ? 'rank-correct' : 'rank-wrong');
            }

            if (iso === correct[i]) {
                el.classList.add('correct');
            } else {
                el.classList.add('wrong');
            }

            // Disable drag
            el.setAttribute('draggable', 'false');
            el.style.cursor = 'default';
        });

        if (isCorrect) {
            GeoGame.addCorrect();
        }
        GeoGame.addAnswered();

        var feedbackText = isCorrect
            ? (T['ord.correct'] || '✅ Correct order!')
            : (T['ord.wrong'] || '❌ Wrong order');
        feedbackText += '  —  ' + (T['ord.score'] || 'Score') + ': ' + score + '/10';

        showFeedback(isCorrect ? 'correct' : 'wrong', feedbackText);

        // Hide confirm, show Next
        document.getElementById('btn-confirm').style.display = 'none';
        var nextBtn = document.getElementById('btn-next');
        if (nextBtn) nextBtn.style.display = '';

        GeoReview.snapshot();
    }

    function nextQuestion() {
        currentIdx++;
        showQuestion();
    }

    function showFeedback(cls, text) {
        var el = document.getElementById('ordering-feedback');
        el.className = 'ordering-feedback ' + cls;
        el.textContent = text;
    }

    function clearFeedback() {
        var el = document.getElementById('ordering-feedback');
        el.className = 'ordering-feedback';
        el.textContent = '';
    }

    function saveResult() {
        var elapsed = Date.now() - GeoGame.startTime;
        var isDaily = GAME_CONFIG && GAME_CONFIG.daily;
        var avgScore = questions.length > 0 ? totalScore / questions.length : 0;
        var isRanked = GeoGame.settings.timeLimit > 0;
        var payload = {
            game_type: 'ordering',
            mode: isDaily ? 'daily' : 'solo',
            score: GeoGame.correct,
            total: GeoGame.total,
            accuracy: GeoGame.total > 0 ? GeoGame.correct / GeoGame.total : 0,
            time_ms: elapsed,
            config: {
                continent: GeoGame.settings.continent,
                questions: questions.length,
                avg_score: Math.round(avgScore * 10) / 10
            },
            ranked: isRanked,
            num_questions: questions.length
        };
        if (isDaily) { _setDailyCache(GeoGame.correct, GeoGame.total, elapsed); }
        fetch('/api/matches/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (isDaily) {
                var isAnon = !data.saved;
                GeoResults.buildDaily(GeoGame.correct, GeoGame.total, elapsed, { isAnon: isAnon });
                startCountdown();
            }
        }).catch(function () {
            if (isDaily) {
                GeoResults.buildDaily(GeoGame.correct, GeoGame.total, elapsed, { isAnon: true });
                startCountdown();
            }
        });
    }

    return { confirm: confirm, next: nextQuestion };
})();
