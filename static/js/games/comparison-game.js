/* ============================================================
   GeoFreak — Comparison Game
   Player picks which of 2 countries has the higher stat.
   ============================================================ */

var ComparisonGame = (function () {
    var questions = [];
    var currentIdx = 0;
    var answered = false;

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
        // Hide game area and HUD, show results overlay with previous result + countdown
        document.getElementById('game-area').style.display = 'none';
        document.getElementById('game-hud').style.display = 'none';
        var overlay = document.getElementById('results-overlay');
        overlay.style.display = 'flex';

        var pct = result.total > 0 ? Math.round((result.score / result.total) * 100) : 0;
        var elapsed = Math.round(result.time_ms / 1000);
        var m = Math.floor(elapsed / 60);
        var s = elapsed % 60;
        var icon = pct >= 80 ? '🏆' : pct >= 50 ? '👏' : '💪';

        document.querySelector('.results-icon').textContent = icon;
        document.getElementById('result-correct').textContent = result.score;
        document.getElementById('result-total').textContent = result.total;
        document.getElementById('result-pct').textContent = pct + '%';
        document.getElementById('result-time').textContent = m + ':' + (s < 10 ? '0' : '') + s;

        // Replace actions with countdown and "come back tomorrow" message
        var actions = document.querySelector('.results-actions');
        actions.innerHTML =
            '<div class="daily-done-msg">' +
            '<p>' + (T['daily.already_played'] || 'You already completed today\'s challenge!') + '</p>' +
            '<p class="daily-countdown" id="daily-countdown"></p>' +
            '<a href="/games" class="btn-outline-dark">' + (T['game.others'] || 'Other games') + '</a>' +
            '</div>';
        startCountdown();
    }

    function showAnonMessage() {
        // After game ends for anonymous user, show signup prompt
        var actions = document.querySelector('.results-actions');
        if (!actions || !(GAME_CONFIG && GAME_CONFIG.daily)) return;
        var signupHtml =
            '<div class="daily-anon-msg">' +
            '<p>' + (T['daily.register_prompt'] || 'Register to save your progress!') + '</p>' +
            '<a href="/auth/register" class="btn btn-primary">' + (T['daily.register_btn'] || 'Sign up') + '</a>' +
            '</div>';
        actions.insertAdjacentHTML('beforeend', signupHtml);
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
                if (!data.saved) {
                    // Anonymous user — show register prompt
                    showAnonMessage();
                } else {
                    // Logged-in user — show countdown instead of replay
                    var actions = document.querySelector('.results-actions');
                    actions.innerHTML =
                        '<div class="daily-done-msg">' +
                        '<p class="daily-countdown" id="daily-countdown"></p>' +
                        '<a href="/games" class="btn-outline-dark">' + (T['game.others'] || 'Other games') + '</a>' +
                        '</div>';
                    startCountdown();
                }
            }
        }).catch(function () {});
    }

    return { pick: pick };
})();
