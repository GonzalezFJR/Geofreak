/* ============================================================
   GeoFreak — Comparison Game
   Player picks which of 2 countries has the higher stat.
   ============================================================ */

var ComparisonGame = (function () {
    var questions = [];
    var currentIdx = 0;
    var answered = false;

    /* ── SVG Star helpers ─────────────────────────────────── */
    var _halfStarId = 0;
    function starSVG(type) {
        // type: 'full', 'half', 'empty'
        var w = 28, h = 28;
        var pts = '14,3 17.5,10 25,11.5 19.5,17 21,24.5 14,20.5 7,24.5 8.5,17 3,11.5 10.5,10';
        if (type === 'full') {
            return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">' +
                '<polygon points="'+pts+'" fill="#f59e0b" stroke="#f59e0b" stroke-width="1.2" stroke-linejoin="round"/>' +
                '</svg>';
        }
        if (type === 'half') {
            var uid = 'hs' + (++_halfStarId);
            return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">' +
                '<defs><clipPath id="'+uid+'-l"><rect x="0" y="0" width="14" height="28"/></clipPath>' +
                '<clipPath id="'+uid+'-r"><rect x="14" y="0" width="14" height="28"/></clipPath></defs>' +
                '<polygon points="'+pts+'" fill="#f59e0b" stroke="#f59e0b" stroke-width="1.2" stroke-linejoin="round" clip-path="url(#'+uid+'-l)"/>' +
                '<polygon points="'+pts+'" fill="none" stroke="#f59e0b" stroke-width="1.2" stroke-linejoin="round" clip-path="url(#'+uid+'-r)"/>' +
                '</svg>';
        }
        // empty
        return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 28 28" xmlns="http://www.w3.org/2000/svg">' +
            '<polygon points="'+pts+'" fill="none" stroke="#d1d5db" stroke-width="1.2" stroke-linejoin="round"/>' +
            '</svg>';
    }

    function renderStars(score, total) {
        // 10 questions → each correct = 0.5 star out of max 5
        var stars = total > 0 ? (score / total) * 5 : 0;
        var fullCount = Math.floor(stars);
        var hasHalf = (stars - fullCount) >= 0.5;
        var emptyCount = 5 - fullCount - (hasHalf ? 1 : 0);
        var html = '<div class="daily-stars">';
        for (var i = 0; i < fullCount; i++) html += starSVG('full');
        if (hasHalf) html += starSVG('half');
        for (var j = 0; j < emptyCount; j++) html += starSVG('empty');
        html += '</div>';
        return html;
    }

    function starsText(score, total) {
        var stars = total > 0 ? (score / total) * 5 : 0;
        var fullCount = Math.floor(stars);
        var hasHalf = (stars - fullCount) >= 0.5;
        var emptyCount = 5 - fullCount - (hasHalf ? 1 : 0);
        var txt = '';
        for (var i = 0; i < fullCount; i++) txt += '★';
        if (hasHalf) txt += '⯨';
        for (var j = 0; j < emptyCount; j++) txt += '☆';
        return txt;
    }

    /* ── Format elapsed time ──────────────────────────────── */
    function fmtTime(ms) {
        var sec = Math.round(ms / 1000);
        var m = Math.floor(sec / 60);
        var s = sec % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    /* ── Build daily results section ──────────────────────── */
    function buildDailyResults(score, total, timeMs, opts) {
        // opts: { isAnon, isReplay }
        var pct = total > 0 ? Math.round((score / total) * 100) : 0;
        var icon = pct >= 80 ? '🏆' : pct >= 50 ? '👏' : '💪';

        // Hide the normal stats grid
        var normalStats = document.getElementById('results-stats-normal');
        if (normalStats) normalStats.style.display = 'none';

        // Set icon & title
        document.querySelector('.results-icon').textContent = icon;

        // Build daily section
        var section = document.getElementById('daily-results-section');
        section.style.display = '';
        section.innerHTML =
            renderStars(score, total) +
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

        // Share button
        html += '<div class="daily-share-row">' +
            '<button class="btn-daily-share" id="btn-daily-share" onclick="ComparisonGame.shareResults()">' +
                '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg> ' +
                (T['daily.share'] || 'Share results') +
            '</button>' +
            '<button class="btn-daily-copy" id="btn-daily-copy" onclick="ComparisonGame.copyResults()">' +
                '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> ' +
                (T['daily.copy'] || 'Copy') +
            '</button>' +
            '</div>';

        // Countdown
        html += '<div class="daily-countdown-wrap">' +
            '<p class="daily-countdown" id="daily-countdown"></p>' +
            '</div>';

        // Auth-dependent button
        if (opts && opts.isAnon) {
            html += '<a href="/auth/register" class="btn-daily-register">' +
                (T['daily.register_btn'] || 'Sign up') +
                '</a>' +
                '<p class="daily-register-hint">' + (T['daily.register_prompt'] || 'Register to save your progress!') + '</p>';
        } else {
            html += '<a href="/profile" class="btn-daily-stats">' +
                (T['daily.view_stats'] || '📊 View my stats') +
                '</a>';
        }

        // Other games — subtle link
        html += '<a href="/games" class="daily-other-games">' + (T['game.others'] || 'Other games') + '</a>';

        actions.innerHTML = html;

        // Start countdown
        startCountdown();

        // Store result for share
        ComparisonGame._lastResult = { score: score, total: total, timeMs: timeMs };
    }

    function init() {
        GeoGame.init({ onStart: loadData });
    }
    init();

    function loadData(settings) {
        var isDaily = GAME_CONFIG && GAME_CONFIG.daily;
        if (isDaily) {
            fetch('/api/daily-challenge')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.already_played) {
                        showAlreadyPlayed(data.result);
                        return;
                    }
                    questions = data.questions || [];
                    currentIdx = 0;
                    GeoGame.setTotal(questions.length);
                    showQuestion();
                });
        } else {
            var num = settings.maxItems || 10;
            var continent = settings.continent || 'all';
            var difficulty = settings.difficulty || 'normal';
            fetch('/api/quiz/comparison?num=' + num + '&continent=' + continent + '&difficulty=' + difficulty)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    questions = data.questions || [];
                    currentIdx = 0;
                    GeoGame.setTotal(questions.length);
                    showQuestion();
                });
        }
    }

    function showAlreadyPlayed(result) {
        document.getElementById('game-area').style.display = 'none';
        document.getElementById('game-hud').style.display = 'none';
        document.getElementById('results-overlay').style.display = 'flex';
        buildDailyResults(result.score, result.total, result.time_ms, { isAnon: false, isReplay: true });
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
            saveResult();
            GeoGame.endGame();
            return;
        }
        answered = false;
        var q = questions[currentIdx];

        document.getElementById('q-current').textContent = currentIdx + 1;
        document.getElementById('q-total').textContent = questions.length;

        var labelKey = T['stat.label_key'] || 'label_es';
        var descKey = labelKey.replace('label_', 'description_');
        var statLabel = q.stat_info[labelKey].toLowerCase();
        var statDesc = q.stat_info[descKey] || '';

        document.getElementById('comparison-prompt').innerHTML =
            (T['cmp.prompt'] || '').replace('{stat}', statLabel);

        // Add description tooltip to stat name in prompt
        if (statDesc) {
            var promptEl = document.getElementById('comparison-prompt');
            var em = promptEl.querySelector('em');
            if (em) {
                em.classList.add('stat-tooltip-trigger');
                em.setAttribute('data-tooltip', statDesc);
                bindTooltipTrigger(em);
            }
        }

        var container = document.getElementById('comparison-cards');
        container.innerHTML = '';

        q.countries.forEach(function (c) {
            var displayName = GeoUtils.getLocalName(c);
            var card = document.createElement('div');
            card.className = 'comparison-card';
            card.setAttribute('data-iso', c.iso_a3);
            card.innerHTML =
                '<div class="comparison-flag">' + (c.flag_emoji || '🏳️') + '</div>' +
                '<div class="comparison-name">' + displayName + '</div>' +
                '<div class="comparison-value" id="val-' + c.iso_a3 + '"></div>';
            card.addEventListener('click', function () {
                pick(c.iso_a3);
            });
            container.appendChild(card);
        });

        clearFeedback();
    }

    function pick(iso) {
        if (answered) return;
        answered = true;

        var q = questions[currentIdx];
        var correct = q.correct_iso;
        var isCorrect = iso === correct;

        if (isCorrect) {
            GeoGame.addCorrect();
        }

        // Reveal values
        q.countries.forEach(function (c) {
            var valEl = document.getElementById('val-' + c.iso_a3);
            if (valEl) {
                valEl.textContent = GeoUtils.formatValue(q.values[c.iso_a3], q.stat_info.format);
                valEl.style.display = 'block';
            }
        });

        // Highlight cards
        var cards = document.querySelectorAll('.comparison-card');
        cards.forEach(function (card) {
            var cardIso = card.getAttribute('data-iso');
            if (cardIso === correct) {
                card.classList.add('correct');
            }
            if (cardIso === iso && !isCorrect) {
                card.classList.add('wrong');
            }
        });

        showFeedback(
            isCorrect ? 'correct' : 'wrong',
            isCorrect ? (T['cmp.correct'] || '✅ Correct!') : (T['cmp.wrong'] || '❌ Wrong')
        );

        setTimeout(function () {
            currentIdx++;
            showQuestion();
        }, 1800);
    }

    function showFeedback(cls, text) {
        var el = document.getElementById('comparison-feedback');
        el.className = 'comparison-feedback ' + cls;
        el.textContent = text;
    }

    function clearFeedback() {
        var el = document.getElementById('comparison-feedback');
        el.className = 'comparison-feedback';
        el.textContent = '';
    }

    function saveResult() {
        var elapsed = Date.now() - GeoGame.startTime;
        var isDaily = GAME_CONFIG && GAME_CONFIG.daily;
        var payload = {
            game_type: 'comparison',
            mode: isDaily ? 'daily' : 'solo',
            score: GeoGame.correct,
            total: GeoGame.total,
            accuracy: GeoGame.total > 0 ? GeoGame.correct / GeoGame.total : 0,
            time_ms: elapsed,
            config: { continent: GeoGame.settings.continent, questions: questions.length }
        };
        fetch('/api/matches/result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (isDaily) {
                var isAnon = !data.saved;
                buildDailyResults(GeoGame.correct, GeoGame.total, elapsed, { isAnon: isAnon });
            }
        }).catch(function () {
            if (isDaily) {
                buildDailyResults(GeoGame.correct, GeoGame.total, elapsed, { isAnon: true });
            }
        });
    }

    /* ── Share / Copy ─────────────────────────────────────── */
    function getShareText() {
        var r = ComparisonGame._lastResult;
        if (!r) return '';
        var template = T['daily.share_text'] || 'I got {score}/{total} on today\'s GeoFreak daily challenge';
        var text = template.replace('{score}', r.score).replace('{total}', r.total);
        text += '\n' + starsText(r.score, r.total);
        text += '\n⏱️ ' + fmtTime(r.timeMs);
        text += '\nhttps://geofreak.app/games/daily';
        return text;
    }

    function shareResults() {
        var text = getShareText();
        var title = T['daily.share_title'] || '🌍 GeoFreak — Daily Challenge';
        if (navigator.share) {
            navigator.share({ title: title, text: text }).catch(function () {});
        } else {
            // Fallback: copy to clipboard
            copyResults();
        }
    }

    function copyResults() {
        var text = getShareText();
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function () {
                var btn = document.getElementById('btn-daily-copy');
                if (btn) {
                    btn.textContent = T['daily.copied'] || '¡Copiado!';
                    setTimeout(function () {
                        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> ' + (T['daily.copy'] || 'Copy');
                    }, 2000);
                }
            });
        }
    }

    return {
        pick: pick,
        shareResults: shareResults,
        copyResults: copyResults,
        _lastResult: null
    };
})();
