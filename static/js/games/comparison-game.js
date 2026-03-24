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
        var num = settings.maxItems || 10;
        var continent = settings.continent || 'all';
        fetch('/api/quiz/comparison?num=' + num + '&continent=' + continent)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                questions = data.questions || [];
                currentIdx = 0;
                GeoGame.setTotal(questions.length);
                showQuestion();
            });
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
        var statLabel = q.stat_info[labelKey];
        var statDesc = q.stat_info[descKey] || '';

        document.getElementById('comparison-prompt').innerHTML =
            (T['cmp.prompt'] || '').replace('{stat}', statLabel);

        // Add description tooltip to stat name in prompt
        if (statDesc) {
            var promptEl = document.getElementById('comparison-prompt');
            var strong = promptEl.querySelector('strong');
            if (strong) {
                strong.classList.add('stat-tooltip-trigger');
                strong.setAttribute('data-tooltip', statDesc);
                strong.addEventListener('click', function(e) {
                    e.stopPropagation();
                    toggleTooltip(this);
                });
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
        var payload = {
            game_type: 'comparison',
            mode: 'solo',
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
        }).catch(function () {});
    }

    return { pick: pick };
})();
