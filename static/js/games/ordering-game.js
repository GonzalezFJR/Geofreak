/* ============================================================
   GeoFreak — Ordering Game
   Player must sort 5 countries by a given statistic.
   ============================================================ */

var OrderingGame = (function () {
    var questions = [];
    var currentIdx = 0;
    var dragSrcEl = null;

    function init() {
        GeoGame.init({ onStart: loadData });
    }
    init();

    function loadData(settings) {
        var num = settings.maxItems || 10;
        var continent = settings.continent || 'all';
        fetch('/api/quiz/ordering?num=' + num + '&continent=' + continent)
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
        var q = questions[currentIdx];
        document.getElementById('q-current').textContent = currentIdx + 1;
        document.getElementById('q-total').textContent = questions.length;

        var direction = q.ascending
            ? (T['ord.prompt_asc'] || 'Sort by <strong>{stat}</strong> ↑').replace('{stat}', q.stat_info[T['stat.label_key'] || 'label_es'])
            : (T['ord.prompt_desc'] || 'Sort by <strong>{stat}</strong> ↓').replace('{stat}', q.stat_info[T['stat.label_key'] || 'label_es']);
        document.getElementById('ordering-prompt').innerHTML = direction;

        renderItems(q.countries);
        clearFeedback();
        document.getElementById('btn-confirm').disabled = false;
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
                '<span class="ordering-handle">☰</span>' +
                '<span class="ordering-flag">' + (c.flag_emoji || '🏳️') + '</span>' +
                '<span class="ordering-name">' + ((window.LANG === 'es' && c.name_es) ? c.name_es : c.name) + '</span>';

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
        }
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
        var isCorrect = playerOrder.every(function (iso, i) {
            return iso === correct[i];
        });

        // Show correct/incorrect per item
        items.forEach(function (el, i) {
            var iso = el.getAttribute('data-iso');
            var correctIdx = correct.indexOf(iso);
            var val = q.correct_values[iso];
            var formatted = formatValue(val, q.stat_info.format);

            var badge = document.createElement('span');
            badge.className = 'ordering-value';
            badge.textContent = formatted;
            el.appendChild(badge);

            if (iso === correct[i]) {
                el.classList.add('correct');
            } else {
                el.classList.add('wrong');
            }
        });

        if (isCorrect) {
            GeoGame.addCorrect();
            showFeedback('correct', T['ord.correct'] || '✅ Correct order!');
        } else {
            showFeedback('wrong', T['ord.wrong'] || '❌ Wrong order');
        }

        document.getElementById('btn-confirm').disabled = true;
        setTimeout(function () {
            currentIdx++;
            showQuestion();
        }, 2000);
    }

    function formatValue(val, fmt) {
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
        var payload = {
            game_type: 'ordering',
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

    return { confirm: confirm };
})();
