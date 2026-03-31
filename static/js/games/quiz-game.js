/* ============================================================
   GeoFreak — Quiz Game Engine
   Shared by: Flags quiz & Outline quiz
   Each game page passes a config with displayItem(country, el).
   ============================================================ */

var QuizGame = (function () {
    var queue = [];
    var skipped = [];       // items skipped to retry later
    var allCountries = [];  // all loaded countries for validation
    var currentIdx = 0;
    var displayFn = null;
    var answerFn = null;
    var inRetryMode = false;

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

        // Prevent reveal button from closing keyboard
        var revealBtn = document.querySelector('.btn-reveal');
        if (revealBtn) {
            revealBtn.addEventListener('mousedown', function (e) { e.preventDefault(); });
        }
        // Prevent skip button from closing keyboard
        var skipBtn = document.querySelector('.btn-skip');
        if (skipBtn) {
            skipBtn.addEventListener('mousedown', function (e) { e.preventDefault(); });
        }
    }

    function loadData(settings) {
        var cust = (typeof GeoCustomize !== 'undefined') ? GeoCustomize.getState() : {};
        var isSubnational = cust.dataset === 'regions';
        var apiDataset = isSubnational ? cust.subDataset : 'countries';

        skipped = [];
        inRetryMode = false;

        if (isSubnational) {
            fetch('/api/map-game/data?dataset=' + encodeURIComponent(apiDataset))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    var entities = data.map(function (e) {
                        return Object.assign({}, e, { iso_a3: e.id, entity_type: 'country', flag_emoji: '' });
                    });
                    allCountries = entities;
                    GeoUtils.shuffle(entities);
                    var max = settings.maxItems || 0;
                    queue = max > 0 ? entities.slice(0, max) : entities.slice();
                    currentIdx = 0;
                    GeoGame.setTotal(queue.length);
                    GeoGame.beginPlay();
                    showNext();
                });
        } else {
            var continent = cust.continent || settings.continent;
            var entityType = cust.entityType || 'all';
            fetch('/api/countries')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    allCountries = data;
                    var filtered = GeoUtils.filterByContinent(data, continent);
                    filtered = filtered.filter(function (c) {
                        if (!c.iso_a3 || !c.name) return false;
                        if (entityType !== 'all') return c.entity_type === entityType;
                        if (c.entity_type && c.entity_type !== 'country') return false;
                        return true;
                    });
                    GeoUtils.shuffle(filtered);
                    var max = settings.maxItems || 0;
                    queue = max > 0 ? filtered.slice(0, max) : filtered.slice();
                    currentIdx = 0;
                    GeoGame.setTotal(queue.length);
                    GeoGame.beginPlay();
                    showNext();
                });
        }
    }

    function showNext(focusInput) {
        // Check if we finished the main queue
        if (currentIdx >= queue.length) {
            // If there are skipped items, cycle back to them
            if (skipped.length > 0 && !inRetryMode) {
                inRetryMode = true;
                queue = skipped.slice();
                skipped = [];
                currentIdx = 0;
                GeoGame.setTotal(queue.length);
            } else if (skipped.length > 0) {
                // Already in retry mode, cycle again
                queue = skipped.slice();
                skipped = [];
                currentIdx = 0;
                GeoGame.setTotal(queue.length);
            } else {
                GeoGame.endGame();
                return;
            }
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
        // Only focus input if requested (default: true)
        if (focusInput !== false) {
            input.focus();
        }
        clearFeedback();
    }

    /** Check if input matches any known country, return the matched country or null */
    function findMatchingCountry(normalised) {
        for (var i = 0; i < allCountries.length; i++) {
            var c = allCountries[i];
            var names = answerFn(c);
            if (names.has(normalised)) {
                return c;
            }
        }
        return null;
    }

    function checkAnswer() {
        var input = document.getElementById('answer-input');
        var answer = input.value.trim();
        if (!answer) return;

        var country    = queue[currentIdx];
        var acceptable = answerFn(country);
        var normalised = GeoUtils.normalize(answer);

        if (acceptable.has(normalised)) {
            // CORRECT
            GeoGame.addCorrect();
            input.className = 'correct';
            showFeedback('correct', (T['js.correct_name'] || '✅ Correct! {name}').replace('{name}', GeoUtils.getLocalName(country)));
            GeoReview.snapshot();
            setTimeout(function () { currentIdx++; showNext(); }, 800);
        } else {
            // Check if it's a valid country name (but wrong answer)
            var matched = findMatchingCountry(normalised);
            if (matched) {
                // Valid country, but WRONG - reveal correct answer and move on
                var localName = GeoUtils.getLocalName(country);
                input.value = localName;
                input.className = 'wrong';
                showFeedback('wrong', (T['js.wrong_answer'] || '❌ It was: {name}').replace('{name}', localName));
                GeoReview.snapshot();
                setTimeout(function () { currentIdx++; showNext(); }, 1500);
            } else {
                // Not a recognized country - let them try again
                input.className = 'wrong';
                showFeedback('wrong', T['js.not_recognized'] || '❓ Country not recognized');
                setTimeout(function () { input.className = ''; }, 400);
                input.select();
            }
        }
    }

    /** Next: skip current item and add to retry queue */
    function skip() {
        var country = queue[currentIdx];
        skipped.push(country);
        var input = document.getElementById('answer-input');
        // Only focus if keyboard was already open (input had focus)
        var hadFocus = document.activeElement === input;
        currentIdx++;
        showNext(hadFocus);
    }

    /** Reveal: show the answer and count as failed */
    function reveal() {
        var country = queue[currentIdx];
        var input = document.getElementById('answer-input');
        // Only focus if keyboard was already open (input had focus)
        var hadFocus = document.activeElement === input;
        var localName = GeoUtils.getLocalName(country);
        input.value = localName;
        input.className = 'wrong';
        showFeedback('wrong', (T['js.revealed'] || '👁️ {name}').replace('{name}', localName));
        GeoReview.snapshot();
        // Count as seen but NOT correct (it's a fail)
        setTimeout(function () {
            currentIdx++;
            showNext(hadFocus);
        }, 1500);
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
