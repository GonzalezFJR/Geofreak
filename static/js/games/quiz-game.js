/* ============================================================
   GeoFreak — Quiz Game Engine
   Shared by: Flags quiz & Outline quiz
   Each game page passes a config with displayItem(country, el).
   ============================================================ */

var QuizGame = (function () {
    var queue = [];
    var currentIdx = 0;
    var displayFn = null;
    var answerFn = null;

    /**
     * @param {Object} config
     *   displayItem(country, containerEl)  – render the visual clue
     *   getAnswers(country) – return Set of normalised acceptable names
     */
    function init(config) {
        displayFn = config.displayItem;
        answerFn  = config.getAnswers || function (c) { return GeoUtils.getCountryNames(c); };

        GeoGame.init({ onStart: loadData });

        // Enter to submit
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') checkAnswer();
        });
    }

    function loadData(settings) {
        var cust = (typeof GeoCustomize !== 'undefined') ? GeoCustomize.getState() : {};
        var isSubnational = cust.dataset === 'regions';
        var apiDataset = isSubnational ? cust.subDataset : 'countries';

        if (isSubnational) {
            fetch('/api/map-game/data?dataset=' + encodeURIComponent(apiDataset))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    // map-game/data returns {id, name, name_es, ...}; expose iso_a3 for quiz engine
                    var entities = data.map(function (e) {
                        return Object.assign({}, e, { iso_a3: e.id, entity_type: 'country', flag_emoji: '' });
                    });
                    GeoUtils.shuffle(entities);
                    var max = settings.maxItems || 0;
                    queue = max > 0 ? entities.slice(0, max) : entities;
                    currentIdx = 0;
                    GeoGame.setTotal(queue.length);
                    showNext();
                });
        } else {
            var continent = cust.continent || settings.continent;
            var entityType = cust.entityType || 'all';
            fetch('/api/countries')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var filtered = GeoUtils.filterByContinent(data, continent);
                    filtered = filtered.filter(function (c) {
                        if (!c.iso_a3 || !c.name) return false;
                        if (entityType !== 'all') return c.entity_type === entityType;
                        if (c.entity_type && c.entity_type !== 'country') return false;
                        return true;
                    });
                    GeoUtils.shuffle(filtered);
                    var max = settings.maxItems || 0;
                    queue = max > 0 ? filtered.slice(0, max) : filtered;
                    currentIdx = 0;
                    GeoGame.setTotal(queue.length);
                    showNext();
                });
        }
    }

    function showNext() {
        if (currentIdx >= queue.length) {
            GeoGame.endGame();
            return;
        }
        var country = queue[currentIdx];
        var display = document.getElementById('quiz-display');
        display.innerHTML = '';
        displayFn(country, display);

        document.getElementById('q-current').textContent = currentIdx + 1;
        document.getElementById('q-total').textContent   = queue.length;

        var input = document.getElementById('answer-input');
        input.value = '';
        input.className = '';
        input.focus();
        clearFeedback();
    }

    function checkAnswer() {
        var input = document.getElementById('answer-input');
        var answer = input.value.trim();
        if (!answer) return;

        var country    = queue[currentIdx];
        var acceptable = answerFn(country);
        var normalised = GeoUtils.normalize(answer);

        if (acceptable.has(normalised)) {
            GeoGame.addCorrect();
            input.className = 'correct';
            showFeedback('correct', (T['js.correct_name'] || '✅ Correct! {name}').replace('{name}', GeoUtils.getLocalName(country)));
            GeoReview.snapshot();
            setTimeout(function () { currentIdx++; showNext(); }, 800);
        } else {
            input.className = 'wrong';
            showFeedback('wrong', T['js.wrong_retry'] || '❌ Wrong, try again');
            setTimeout(function () { input.className = ''; }, 400);
            input.select();
        }
    }

    function skip() {
        var country = queue[currentIdx];
        showFeedback('skipped', (T['js.skipped'] || '⏭️ It was: {name}').replace('{name}', GeoUtils.getLocalName(country)));
        GeoReview.snapshot();
        setTimeout(function () { currentIdx++; showNext(); }, 1200);
    }

    function reveal() {
        var country = queue[currentIdx];
        var input = document.getElementById('answer-input');
        var localName = GeoUtils.getLocalName(country);
        input.value = localName;
        input.className = 'wrong';
        showFeedback('wrong', (T['js.revealed'] || '👁️ {name}').replace('{name}', localName));
        GeoReview.snapshot();
        // Count as seen but NOT correct (it's a fail)
        setTimeout(function () { currentIdx++; showNext(); }, 1500);
    }

    function showFeedback(cls, text) {
        var el = document.getElementById('quiz-feedback');
        el.className = 'quiz-feedback ' + cls;
        el.textContent = text;
    }
    function clearFeedback() {
        var el = document.getElementById('quiz-feedback');
        el.className = 'quiz-feedback';
        el.textContent = '';
    }

    return { init: init, skip: skip, reveal: reveal, checkAnswer: checkAnswer };
})();
