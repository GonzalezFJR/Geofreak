/* ============================================================
   GeoFreak — Tournament Play Controller
   Multi-round PvP with WebSocket, round transitions, scoreboard.
   ============================================================ */
(function () {
    var TID = window.TRN_ID;
    var STATUS = window.TRN_STATUS;
    var TOTAL_ROUNDS = window.TRN_TOTAL_ROUNDS;
    var CURRENT_ROUND = window.TRN_CURRENT_ROUND;
    var USER_ID = window.USER_ID;
    var CREATED_BY = window.TRN_CREATED_BY;
    var T = window.TRN_T || {};

    var ws = null;
    var questions = [];
    var currentIdx = 0;
    var myRoundScore = 0;
    var currentRound = CURRENT_ROUND;
    var currentGameType = '';
    var playerUsernames = {};
    var scoreboard = {};       // {uid: total}
    var opponentProgress = {}; // {uid: {round, qi, score}}
    var dragSrcEl = null;

    init();

    function init() {
        var shareInput = document.getElementById('share-url');
        if (shareInput) shareInput.value = window.location.origin + '/tournaments/' + TID;

        var btnCopy = document.getElementById('btn-copy-url');
        if (btnCopy) btnCopy.addEventListener('click', function () {
            navigator.clipboard.writeText(window.location.origin + '/tournaments/' + TID).catch(function () {});
            btnCopy.textContent = '✓';
            setTimeout(function () { btnCopy.textContent = T.copy || 'Copy'; }, 1500);
        });

        var btnCancel = document.getElementById('btn-cancel-trn');
        if (btnCancel) btnCancel.addEventListener('click', function () {
            fetch('/api/tournaments/' + TID + '/cancel', { method: 'POST' })
                .then(function () { window.location.href = '/tournaments'; });
        });

        var btnStart = document.getElementById('btn-start-trn');
        if (btnStart) btnStart.addEventListener('click', function () {
            btnStart.disabled = true;
            btnStart.textContent = T.started || 'Starting…';
            fetch('/api/tournaments/' + TID + '/start', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.started) {
                        alert(data.detail || 'Error');
                        btnStart.disabled = false;
                    }
                });
        });

        var btnConfirm = document.getElementById('btn-trn-confirm-order');
        if (btnConfirm) btnConfirm.addEventListener('click', submitOrderingAnswer);

        connectWebSocket();

        if (STATUS === 'active' && currentRound > 0) {
            fetchStateAndLoadRound();
        }
    }

    // ── WebSocket ───────────────────────────────────────────
    function connectWebSocket() {
        var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(proto + '//' + window.location.host + '/ws/tournament/' + TID);
        ws.onopen = function () {
            setInterval(function () { if (ws.readyState === WebSocket.OPEN) ws.send('ping'); }, 30000);
        };
        ws.onmessage = function (e) {
            var msg; try { msg = JSON.parse(e.data); } catch (x) { return; }
            handleMsg(msg);
        };
        ws.onclose = function () { setTimeout(connectWebSocket, 2000); };
    }

    function handleMsg(msg) {
        switch (msg.type) {
            case 'player_joined':
                playerUsernames = msg.player_usernames || {};
                updateWaitingPlayerList();
                var btnS = document.getElementById('btn-start-trn');
                if (btnS && (msg.players || []).length >= 2) btnS.disabled = false;
                break;

            case 'tournament_started':
                currentRound = msg.round_number;
                TOTAL_ROUNDS = msg.total_rounds || TOTAL_ROUNDS;
                document.getElementById('trn-waiting').style.display = 'none';
                document.getElementById('trn-game').style.display = 'block';
                fetchStateAndLoadRound();
                break;

            case 'opponent_progress':
                if (!opponentProgress[msg.user_id]) opponentProgress[msg.user_id] = {};
                opponentProgress[msg.user_id].score = msg.score;
                opponentProgress[msg.user_id].qi = msg.question_index;
                updateScoreboard();
                break;

            case 'player_round_finished':
                showFeedback((playerUsernames[msg.user_id] || T.opponent) + ' — ' + msg.score + ' ' + T.points, 'info');
                break;

            case 'round_finished':
                showRoundTransition(msg);
                break;

            case 'tournament_finished':
                showFinalResults(msg.scoreboard, msg.player_usernames);
                break;

            case 'tournament_cancelled':
                showFeedback(T.cancelled || 'Cancelled', 'error');
                setTimeout(function () { window.location.href = '/tournaments'; }, 1500);
                break;

            case 'user_connected': break;
            case 'user_disconnected': break;
            case 'pong': break;
        }
    }

    function updateWaitingPlayerList() {
        var el = document.getElementById('trn-player-list');
        if (!el) return;
        el.innerHTML = '';
        for (var uid in playerUsernames) {
            var chip = document.createElement('div');
            chip.className = 'trn-player-chip';
            chip.textContent = playerUsernames[uid];
            el.appendChild(chip);
        }
    }

    // ── Fetch state & load round ────────────────────────────
    function fetchStateAndLoadRound() {
        fetch('/api/tournaments/' + TID)
            .then(function (r) { return r.json(); })
            .then(function (tourn) {
                playerUsernames = tourn.player_usernames || {};
                scoreboard = tourn.scoreboard || {};
                currentRound = tourn.current_round;
                TOTAL_ROUNDS = tourn.number_of_rounds;
                updateScoreboard();
                loadRound(currentRound);
            });
    }

    function loadRound(roundNum) {
        document.getElementById('trn-round-num').textContent = roundNum;
        document.getElementById('trn-round-total').textContent = TOTAL_ROUNDS;
        document.getElementById('trn-round-transition').style.display = 'none';
        document.getElementById('trn-question-area').style.display = 'block';

        fetch('/api/tournaments/' + TID + '/round/' + roundNum + '/questions')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                questions = data.questions || [];
                currentGameType = data.game_type;
                currentIdx = 0;
                myRoundScore = 0;
                opponentProgress = {};

                var badge = document.getElementById('trn-game-type-badge');
                badge.textContent = currentGameType === 'ordering' ? (T.ordering || 'Ordering') : (T.comparison || 'Comparison');

                document.getElementById('tq-total').textContent = questions.length;
                showQuestion();
            });
    }

    // ── Scoreboard ──────────────────────────────────────────
    function updateScoreboard() {
        var el = document.getElementById('trn-scoreboard');
        if (!el) return;
        var entries = [];
        for (var uid in scoreboard) {
            entries.push({
                uid: uid,
                name: uid === USER_ID ? (T.you || 'You') : (playerUsernames[uid] || T.opponent),
                total: parseInt(scoreboard[uid] || 0, 10),
                roundScore: uid === USER_ID ? myRoundScore : (opponentProgress[uid] ? opponentProgress[uid].score || 0 : 0),
                isYou: uid === USER_ID
            });
        }
        entries.sort(function (a, b) { return b.total - a.total; });

        var html = '';
        entries.forEach(function (e) {
            html += '<div class="sb-row' + (e.isYou ? ' sb-you' : '') + '">' +
                '<span class="sb-name">' + esc(e.name) + '</span>' +
                '<span class="sb-round-score">' + e.roundScore + '</span>' +
                '<span class="sb-total-score">' + e.total + '</span>' +
                '</div>';
        });
        el.innerHTML = '<div class="sb-header"><span></span><span>R' + currentRound + '</span><span>Total</span></div>' + html;
    }

    // ── Show question ───────────────────────────────────────
    function showQuestion() {
        if (currentIdx >= questions.length) return;
        var q = questions[currentIdx];
        document.getElementById('tq-current').textContent = currentIdx + 1;
        document.getElementById('trn-feedback').style.display = 'none';

        var promptEl = document.getElementById('trn-prompt');
        var orderEl = document.getElementById('trn-ordering-items');
        var confirmBtn = document.getElementById('btn-trn-confirm-order');
        var compEl = document.getElementById('trn-comparison-cards');

        if (currentGameType === 'ordering') {
            compEl.style.display = 'none';
            orderEl.style.display = 'flex';
            confirmBtn.style.display = 'inline-flex';
            confirmBtn.disabled = false;
            var label = q.stat_info[T.stat_label_key || 'label_es'] || q.stat;
            promptEl.innerHTML = (q.ascending ? T.prompt_asc : T.prompt_desc).replace('{stat}', label);
            renderOrderingItems(q.countries);
        } else {
            orderEl.style.display = 'none';
            confirmBtn.style.display = 'none';
            compEl.style.display = 'flex';
            var label2 = q.stat_info[T.stat_label_key || 'label_es'] || q.stat;
            promptEl.innerHTML = (T.cmp_prompt || '').replace('{stat}', label2);
            renderComparisonCards(q.countries);
        }
    }

    // ── Ordering ────────────────────────────────────────────
    function renderOrderingItems(countries) {
        var c = document.getElementById('trn-ordering-items');
        c.innerHTML = '';
        countries.forEach(function (co) {
            var el = document.createElement('div');
            el.className = 'ordering-item';
            el.setAttribute('draggable', 'true');
            el.setAttribute('data-iso', co.iso_a3);
            el.innerHTML = '<span class="ordering-handle">☰</span>' +
                '<span class="ordering-flag">' + (co.flag_emoji || '🏳️') + '</span>' +
                '<span class="ordering-name">' + esc(co.name) + '</span>';
            el.addEventListener('dragstart', dStart);
            el.addEventListener('dragover', dOver);
            el.addEventListener('drop', dDrop);
            el.addEventListener('dragend', dEnd);
            el.addEventListener('touchstart', tStart, { passive: false });
            el.addEventListener('touchmove', tMove, { passive: false });
            el.addEventListener('touchend', tEnd);
            c.appendChild(el);
        });
    }

    function dStart(e) { dragSrcEl = this; this.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', ''); }
    function dOver(e) {
        e.preventDefault();
        var t = closest(e.target);
        if (t && t !== dragSrcEl) {
            var c = document.getElementById('trn-ordering-items'), items = Array.from(c.children);
            if (items.indexOf(dragSrcEl) < items.indexOf(t)) c.insertBefore(dragSrcEl, t.nextSibling);
            else c.insertBefore(dragSrcEl, t);
        }
    }
    function dDrop(e) { e.preventDefault(); }
    function dEnd() { this.classList.remove('dragging'); dragSrcEl = null; }

    var touchEl = null;
    function tStart(e) { e.preventDefault(); touchEl = this; this.classList.add('dragging'); }
    function tMove(e) {
        e.preventDefault();
        if (!touchEl) return;
        var touch = e.touches[0], target = document.elementFromPoint(touch.clientX, touch.clientY);
        var item = closest(target);
        if (item && item !== touchEl) {
            var c = document.getElementById('trn-ordering-items'), items = Array.from(c.children);
            if (items.indexOf(touchEl) < items.indexOf(item)) c.insertBefore(touchEl, item.nextSibling);
            else c.insertBefore(touchEl, item);
        }
    }
    function tEnd() { if (touchEl) touchEl.classList.remove('dragging'); touchEl = null; }
    function closest(el) { while (el && !el.classList.contains('ordering-item')) el = el.parentElement; return el; }

    function submitOrderingAnswer() {
        var items = Array.from(document.getElementById('trn-ordering-items').children);
        var order = items.map(function (el) { return el.getAttribute('data-iso'); });
        document.getElementById('btn-trn-confirm-order').disabled = true;
        submitAnswer(order);
    }

    // ── Comparison ──────────────────────────────────────────
    function renderComparisonCards(countries) {
        var c = document.getElementById('trn-comparison-cards');
        c.innerHTML = '';
        countries.forEach(function (co) {
            var card = document.createElement('div');
            card.className = 'cmp-card';
            card.innerHTML = '<span class="cmp-flag">' + (co.flag_emoji || '🏳️') + '</span>' +
                '<span class="cmp-name">' + esc(co.name) + '</span>';
            card.addEventListener('click', function () {
                c.querySelectorAll('.cmp-card').forEach(function (el) { el.style.pointerEvents = 'none'; });
                submitAnswer(co.iso_a3);
            });
            c.appendChild(card);
        });
    }

    // ── Submit answer ───────────────────────────────────────
    function submitAnswer(answer) {
        fetch('/api/tournaments/' + TID + '/answer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ round_number: currentRound, question_index: currentIdx, answer: answer })
        })
            .then(function (r) { return r.json(); })
            .then(function (res) { handleResult(res); });
    }

    function handleResult(res) {
        if (res.correct) {
            myRoundScore = res.current_score;
            showFeedback(T.correct || '✅', 'correct');
        } else {
            showFeedback(T.wrong || '❌', 'wrong');
        }
        updateScoreboard();

        if (res.is_last) {
            // Wait for round_finished or tournament_finished from WS
            showFeedback(T.waiting_others || 'Waiting for others…', 'info');
            return;
        }
        setTimeout(function () { currentIdx++; showQuestion(); }, 1200);
    }

    function showFeedback(text, type) {
        var el = document.getElementById('trn-feedback');
        el.textContent = text;
        el.className = 'trn-feedback trn-feedback-' + type;
        el.style.display = 'block';
        if (type !== 'info') setTimeout(function () { el.style.display = 'none'; }, 1000);
    }

    // ── Round transition ────────────────────────────────────
    function showRoundTransition(msg) {
        // Update scoreboard with latest
        scoreboard = msg.scoreboard || scoreboard;
        updateScoreboard();

        document.getElementById('trn-question-area').style.display = 'none';
        var trans = document.getElementById('trn-round-transition');
        trans.style.display = 'block';

        document.getElementById('trn-transition-title').textContent =
            (T.round_complete || 'Round complete!').replace('{n}', msg.round_number);

        // Show round scores
        var rsEl = document.getElementById('trn-round-scores');
        var html = '';
        var rs = msg.round_scores || {};
        for (var uid in rs) {
            var name = uid === USER_ID ? (T.you || 'You') : (playerUsernames[uid] || '?');
            html += '<div class="round-score-row' + (uid === USER_ID ? ' is-you' : '') + '">' +
                '<span>' + esc(name) + '</span><span>' + parseInt(rs[uid] || 0, 10) + ' ' + T.points + '</span></div>';
        }
        rsEl.innerHTML = html;

        document.getElementById('trn-next-round-msg').textContent =
            (T.next_round || 'Next round: {type}').replace('{type}',
                msg.next_game_type === 'ordering' ? T.ordering : T.comparison);

        // Auto-load next round after 4 seconds
        currentRound = msg.next_round;
        setTimeout(function () { loadRound(currentRound); }, 4000);
    }

    // ── Final results ───────────────────────────────────────
    function showFinalResults(sb, usernames) {
        document.getElementById('trn-game').style.display = 'none';
        document.getElementById('trn-waiting').style.display = 'none';
        var el = document.getElementById('trn-results');
        el.style.display = 'flex';

        scoreboard = sb || {};
        playerUsernames = usernames || playerUsernames;

        var entries = [];
        for (var uid in sb) {
            entries.push({ uid: uid, score: parseInt(sb[uid] || 0, 10), name: uid === USER_ID ? (T.you || 'You') : (playerUsernames[uid] || '?') });
        }
        entries.sort(function (a, b) { return b.score - a.score; });

        var myScore = parseInt(sb[USER_ID] || 0, 10);
        var topScore = entries.length > 0 ? entries[0].score : 0;

        var icon = document.getElementById('trn-result-icon');
        var title = document.getElementById('trn-result-title');
        if (myScore === topScore && myScore > 0) { icon.textContent = '🏆'; title.textContent = T.win || 'You win!'; }
        else if (myScore === topScore) { icon.textContent = '🤝'; title.textContent = T.draw || 'Draw!'; }
        else { icon.textContent = '🎖️'; title.textContent = T.lose || 'Good game'; }

        var medals = ['🥇', '🥈', '🥉'];
        var html = '';
        entries.forEach(function (e, i) {
            var medal = i < 3 ? medals[i] : (i + 1) + '.';
            html += '<div class="standing-row' + (e.uid === USER_ID ? ' is-you' : '') + '">' +
                '<span class="standing-medal">' + medal + '</span>' +
                '<span class="standing-name">' + esc(e.name) + '</span>' +
                '<span class="standing-score">' + e.score + ' ' + T.points + '</span></div>';
        });
        document.getElementById('trn-final-standings').innerHTML = html;
    }

    function esc(s) { var d = document.createElement('div'); d.appendChild(document.createTextNode(s)); return d.innerHTML; }
})();
