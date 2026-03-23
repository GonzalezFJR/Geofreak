/* ============================================================
   GeoFreak — Duel Play Controller
   Manages WebSocket connection, question rendering, answers,
   and scoreboard for real-time PvP duels.
   ============================================================ */
(function () {
    var DUEL_ID = window.DUEL_ID;
    var STATUS = window.DUEL_STATUS;
    var GAME_TYPE = window.DUEL_GAME_TYPE;
    var USER_ID = window.USER_ID;
    var USER_NAME = window.USER_NAME;
    var T = window.DUEL_T || {};

    var questions = [];
    var currentIdx = 0;
    var myScore = 0;
    var opponentScores = {};   // {user_id: score}
    var opponentProgress = {}; // {user_id: question_index}
    var playerUsernames = {};
    var ws = null;
    var dragSrcEl = null;

    // ── Initialise ──────────────────────────────────────────
    init();

    function init() {
        // Set share URL
        var shareInput = document.getElementById('share-url');
        if (shareInput) {
            shareInput.value = window.location.origin + '/duels/' + DUEL_ID;
        }

        // Copy URL button
        var btnCopy = document.getElementById('btn-copy-url');
        if (btnCopy) {
            btnCopy.addEventListener('click', function () {
                var url = window.location.origin + '/duels/' + DUEL_ID;
                navigator.clipboard.writeText(url).catch(function () {});
                btnCopy.textContent = '✓';
                setTimeout(function () { btnCopy.textContent = T.copy || 'Copy'; }, 1500);
            });
        }

        // Cancel duel
        var btnCancel = document.getElementById('btn-cancel-duel');
        if (btnCancel) {
            btnCancel.addEventListener('click', function () {
                fetch('/api/duels/' + DUEL_ID + '/cancel', { method: 'POST' })
                    .then(function () { window.location.href = '/duels'; })
                    .catch(function () { window.location.href = '/duels'; });
            });
        }

        // Confirm ordering button
        var btnConfirm = document.getElementById('btn-duel-confirm-order');
        if (btnConfirm) {
            btnConfirm.addEventListener('click', submitOrderingAnswer);
        }

        connectWebSocket();

        if (STATUS === 'active') {
            loadQuestions();
        }
    }

    // ── WebSocket ───────────────────────────────────────────
    function connectWebSocket() {
        var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        var url = proto + '//' + window.location.host + '/ws/duel/' + DUEL_ID;
        ws = new WebSocket(url);

        ws.onopen = function () {
            // Send periodic pings
            setInterval(function () {
                if (ws.readyState === WebSocket.OPEN) ws.send('ping');
            }, 30000);
        };

        ws.onmessage = function (event) {
            var msg;
            try { msg = JSON.parse(event.data); } catch (e) { return; }
            handleWSMessage(msg);
        };

        ws.onclose = function () {
            // Reconnect after 2s
            setTimeout(connectWebSocket, 2000);
        };
    }

    function handleWSMessage(msg) {
        switch (msg.type) {
            case 'player_joined':
                playerUsernames = msg.player_usernames || {};
                document.getElementById('duel-waiting').style.display = 'none';
                document.getElementById('duel-game').style.display = 'block';
                loadQuestions();
                break;

            case 'opponent_progress':
                opponentScores[msg.user_id] = msg.score;
                opponentProgress[msg.user_id] = msg.question_index;
                updateScoreboard();
                break;

            case 'player_finished':
                opponentScores[msg.user_id] = msg.score;
                updateScoreboard();
                showFeedback(T.finished || 'Opponent finished!', 'info');
                break;

            case 'duel_finished':
                showResults(msg.scores, msg.player_usernames);
                break;

            case 'duel_cancelled':
                showFeedback(T.cancelled || 'Duel cancelled', 'error');
                setTimeout(function () { window.location.href = '/duels'; }, 1500);
                break;

            case 'user_connected':
                break;

            case 'user_disconnected':
                break;

            case 'pong':
                break;
        }
    }

    // ── Load questions ──────────────────────────────────────
    function loadQuestions() {
        fetch('/api/duels/' + DUEL_ID + '/questions')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                questions = data.questions || [];
                currentIdx = 0;
                myScore = 0;

                // Fetch duel state to get player info
                return fetch('/api/duels/' + DUEL_ID);
            })
            .then(function (r) { return r.json(); })
            .then(function (duel) {
                playerUsernames = duel.player_usernames || {};
                opponentScores = {};
                opponentProgress = {};
                (duel.players || []).forEach(function (pid) {
                    if (pid !== USER_ID) {
                        opponentScores[pid] = duel.current_scores[pid] || 0;
                        opponentProgress[pid] = duel.current_progress[pid] || 0;
                    }
                });
                updateScoreboard();
                document.getElementById('dq-total').textContent = questions.length;
                showQuestion();
            });
    }

    // ── Scoreboard ──────────────────────────────────────────
    function updateScoreboard() {
        var sb = document.getElementById('duel-scoreboard');
        if (!sb) return;
        var html = '<div class="sb-player sb-you">' +
            '<span class="sb-name">' + escapeHtml(T.you || 'You') + '</span>' +
            '<span class="sb-score">' + myScore + '</span>' +
            '</div>';

        for (var uid in opponentScores) {
            var name = playerUsernames[uid] || T.opponent || 'Opponent';
            html += '<div class="sb-player sb-opponent">' +
                '<span class="sb-name">' + escapeHtml(name) + '</span>' +
                '<span class="sb-score">' + opponentScores[uid] + '</span>' +
                '</div>';
        }
        sb.innerHTML = html;
    }

    // ── Show question ───────────────────────────────────────
    function showQuestion() {
        if (currentIdx >= questions.length) {
            return; // done; wait for server
        }
        var q = questions[currentIdx];
        document.getElementById('dq-current').textContent = currentIdx + 1;

        var promptEl = document.getElementById('duel-prompt');
        var orderingEl = document.getElementById('duel-ordering-items');
        var confirmBtn = document.getElementById('btn-duel-confirm-order');
        var compEl = document.getElementById('duel-comparison-cards');
        var feedbackEl = document.getElementById('duel-feedback');
        feedbackEl.style.display = 'none';

        if (GAME_TYPE === 'ordering') {
            compEl.style.display = 'none';
            orderingEl.style.display = 'flex';
            confirmBtn.style.display = 'inline-flex';

            var labelKey = T.stat_label_key || 'label_es';
            var statLabel = q.stat_info[labelKey] || q.stat;
            var prompt = q.ascending
                ? (T.prompt_asc || 'Sort by <strong>{stat}</strong> from lowest to highest ↑')
                : (T.prompt_desc || 'Sort by <strong>{stat}</strong> from highest to lowest ↓');
            promptEl.innerHTML = prompt.replace('{stat}', statLabel);
            confirmBtn.disabled = false;

            renderOrderingItems(q.countries);
        } else {
            orderingEl.style.display = 'none';
            confirmBtn.style.display = 'none';
            compEl.style.display = 'flex';

            var labelKey2 = T.stat_label_key || 'label_es';
            var statLabel2 = q.stat_info[labelKey2] || q.stat;
            promptEl.innerHTML = (T.cmp_prompt || 'Which country has a higher <strong>{stat}</strong>?').replace('{stat}', statLabel2);

            renderComparisonCards(q.countries);
        }
    }

    // ── Ordering ────────────────────────────────────────────
    function renderOrderingItems(countries) {
        var container = document.getElementById('duel-ordering-items');
        container.innerHTML = '';
        countries.forEach(function (c) {
            var el = document.createElement('div');
            el.className = 'ordering-item';
            el.setAttribute('draggable', 'true');
            el.setAttribute('data-iso', c.iso_a3);
            el.innerHTML =
                '<span class="ordering-handle">☰</span>' +
                '<span class="ordering-flag">' + (c.flag_emoji || '🏳️') + '</span>' +
                '<span class="ordering-name">' + escapeHtml(c.name) + '</span>';

            el.addEventListener('dragstart', handleDragStart);
            el.addEventListener('dragover', handleDragOver);
            el.addEventListener('drop', handleDrop);
            el.addEventListener('dragend', handleDragEnd);
            el.addEventListener('touchstart', handleTouchStart, { passive: false });
            el.addEventListener('touchmove', handleTouchMove, { passive: false });
            el.addEventListener('touchend', handleTouchEnd);

            container.appendChild(el);
        });
    }

    function handleDragStart(e) {
        dragSrcEl = this;
        this.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');
    }
    function handleDragOver(e) {
        e.preventDefault();
        var target = closestItem(e.target);
        if (target && target !== dragSrcEl) {
            var container = document.getElementById('duel-ordering-items');
            var items = Array.from(container.children);
            var srcIdx = items.indexOf(dragSrcEl);
            var tgtIdx = items.indexOf(target);
            if (srcIdx < tgtIdx) container.insertBefore(dragSrcEl, target.nextSibling);
            else container.insertBefore(dragSrcEl, target);
        }
    }
    function handleDrop(e) { e.preventDefault(); }
    function handleDragEnd() {
        this.classList.remove('dragging');
        dragSrcEl = null;
    }

    // Touch support
    var touchData = { el: null, clone: null, startY: 0 };
    function handleTouchStart(e) {
        e.preventDefault();
        touchData.el = this;
        touchData.startY = e.touches[0].clientY;
        this.classList.add('dragging');
    }
    function handleTouchMove(e) {
        e.preventDefault();
        if (!touchData.el) return;
        var touch = e.touches[0];
        var container = document.getElementById('duel-ordering-items');
        var items = Array.from(container.children);
        var target = document.elementFromPoint(touch.clientX, touch.clientY);
        var item = closestItem(target);
        if (item && item !== touchData.el) {
            var srcIdx = items.indexOf(touchData.el);
            var tgtIdx = items.indexOf(item);
            if (srcIdx < tgtIdx) container.insertBefore(touchData.el, item.nextSibling);
            else container.insertBefore(touchData.el, item);
        }
    }
    function handleTouchEnd() {
        if (touchData.el) touchData.el.classList.remove('dragging');
        touchData.el = null;
    }

    function closestItem(el) {
        while (el && !el.classList.contains('ordering-item')) el = el.parentElement;
        return el;
    }

    function submitOrderingAnswer() {
        var container = document.getElementById('duel-ordering-items');
        var items = Array.from(container.children);
        var order = items.map(function (el) { return el.getAttribute('data-iso'); });

        var btn = document.getElementById('btn-duel-confirm-order');
        btn.disabled = true;

        fetch('/api/duels/' + DUEL_ID + '/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_index: currentIdx, answer: order })
        })
            .then(function (r) { return r.json(); })
            .then(function (result) {
                handleAnswerResult(result);
            });
    }

    // ── Comparison ──────────────────────────────────────────
    function renderComparisonCards(countries) {
        var container = document.getElementById('duel-comparison-cards');
        container.innerHTML = '';
        countries.forEach(function (c) {
            var card = document.createElement('div');
            card.className = 'cmp-card';
            card.setAttribute('data-iso', c.iso_a3);
            card.innerHTML =
                '<span class="cmp-flag">' + (c.flag_emoji || '🏳️') + '</span>' +
                '<span class="cmp-name">' + escapeHtml(c.name) + '</span>';
            card.addEventListener('click', function () {
                submitComparisonAnswer(c.iso_a3);
                // Disable cards
                container.querySelectorAll('.cmp-card').forEach(function (el) { el.style.pointerEvents = 'none'; });
            });
            container.appendChild(card);
        });
    }

    function submitComparisonAnswer(isoCode) {
        fetch('/api/duels/' + DUEL_ID + '/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_index: currentIdx, answer: isoCode })
        })
            .then(function (r) { return r.json(); })
            .then(function (result) {
                handleAnswerResult(result);
            });
    }

    // ── Answer result ───────────────────────────────────────
    function handleAnswerResult(result) {
        if (result.correct) {
            myScore = result.current_score;
            showFeedback(T.correct || '✅ Correct!', 'correct');
        } else {
            showFeedback(T.wrong || '❌ Wrong', 'wrong');
        }
        updateScoreboard();

        if (result.is_last) {
            // Wait for duel_finished from WebSocket or from API
            setTimeout(function () {
                // Check if duel is already finished
                fetch('/api/duels/' + DUEL_ID)
                    .then(function (r) { return r.json(); })
                    .then(function (duel) {
                        if (duel.status === 'finished') {
                            showResults(duel.current_scores, duel.player_usernames);
                        }
                        // Otherwise wait for WS event
                    });
            }, 1500);
            return;
        }

        // Next question after short delay
        setTimeout(function () {
            currentIdx++;
            showQuestion();
        }, 1200);
    }

    function showFeedback(text, type) {
        var el = document.getElementById('duel-feedback');
        el.textContent = text;
        el.className = 'duel-feedback duel-feedback-' + type;
        el.style.display = 'block';
        setTimeout(function () { el.style.display = 'none'; }, 1000);
    }

    // ── Results ─────────────────────────────────────────────
    function showResults(scores, usernames) {
        document.getElementById('duel-game').style.display = 'none';
        document.getElementById('duel-waiting').style.display = 'none';
        var resultsEl = document.getElementById('duel-results');
        resultsEl.style.display = 'flex';

        var myFinalScore = parseInt(scores[USER_ID] || 0, 10);
        var bestOpponent = 0;
        for (var uid in scores) {
            if (uid !== USER_ID) {
                var s = parseInt(scores[uid] || 0, 10);
                if (s > bestOpponent) bestOpponent = s;
            }
        }

        var icon = document.getElementById('duel-result-icon');
        var title = document.getElementById('duel-result-title');
        if (myFinalScore > bestOpponent) {
            icon.textContent = '🏆';
            title.textContent = T.win || 'You win!';
        } else if (myFinalScore < bestOpponent) {
            icon.textContent = '😞';
            title.textContent = T.lose || 'You lose';
        } else {
            icon.textContent = '🤝';
            title.textContent = T.draw || 'Draw!';
        }

        var scoresEl = document.getElementById('duel-final-scores');
        var html = '';
        for (var pid in scores) {
            var name = pid === USER_ID ? (T.you || 'You') : (usernames[pid] || T.opponent || 'Opponent');
            var cls = pid === USER_ID ? 'is-you' : '';
            html += '<div class="final-score-row ' + cls + '">' +
                '<span class="final-score-name">' + escapeHtml(name) + '</span>' +
                '<span class="final-score-value">' + parseInt(scores[pid] || 0, 10) + ' ' + (T.points || 'pts') + '</span>' +
                '</div>';
        }
        scoresEl.innerHTML = html;
    }

    // ── Util ────────────────────────────────────────────────
    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }
})();
