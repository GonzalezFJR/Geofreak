/* ============================================================
   GeoFreak — Tournament Play Controller v2
   Multi-round PvP with game designer, structure overview,
   pre-game summaries, global scoreboard, all game types.
   ============================================================ */
(function () {
    var TID = window.TRN_ID;
    var STATUS = window.TRN_STATUS;
    var TOTAL_ROUNDS = window.TRN_TOTAL_ROUNDS;
    var CURRENT_ROUND = window.TRN_CURRENT_ROUND;
    var USER_ID = window.USER_ID;
    var CREATED_BY = window.TRN_CREATED_BY;
    var T = window.TRN_T || {};
    var CONFIG = window.TRN_CONFIG || {};
    var roundsConfig = CONFIG.rounds || [];

    var ws = null;
    var questions = [];
    var currentIdx = 0;
    var myRoundScore = 0;
    var currentRound = CURRENT_ROUND;
    var currentGameType = '';
    var playerUsernames = window.TRN_PLAYER_USERNAMES || {};
    var scoreboard = window.TRN_SCOREBOARD || {};
    var roundScores = {};   // {roundNum: {uid: score}}
    var opponentProgress = {};
    var dragSrcEl = null;

    var GAME_ICONS = {
        ordering: '/static/img/icons/ordering.svg',
        comparison: '/static/img/icons/comparison.svg',
        geostats: '/static/img/icons/geostats.svg',
        flags: '/static/img/icons/flags.svg',
        outline: '/static/img/icons/outline.svg'
    };
    var GAME_NAMES = T.game_names || {};

    // Sections
    var sections = ['trn-waiting', 'trn-structure-view', 'trn-pregame-view', 'trn-game', 'trn-scoreboard-view', 'trn-results'];

    function showSection(id) {
        sections.forEach(function (s) {
            var el = document.getElementById(s);
            if (el) el.style.display = s === id ? (s === 'trn-results' ? 'flex' : 'block') : 'none';
        });
    }

    init();

    function init() {
        var shareInput = document.getElementById('share-url');
        if (shareInput) shareInput.value = window.location.origin + '/tournaments/' + TID;

        document.getElementById('btn-copy-url')?.addEventListener('click', function () {
            navigator.clipboard.writeText(window.location.origin + '/tournaments/' + TID).catch(function () {});
            this.textContent = '✓';
            var btn = this;
            setTimeout(function () { btn.textContent = '📋'; }, 1500);
        });

        document.getElementById('btn-copy-code')?.addEventListener('click', function () {
            var code = document.getElementById('trn-room-code')?.textContent || '';
            navigator.clipboard.writeText(code.trim()).catch(function () {});
            this.textContent = '✓';
            var btn = this;
            setTimeout(function () { btn.textContent = T.copy_code || 'Copy'; }, 1500);
        });

        document.getElementById('btn-cancel-trn')?.addEventListener('click', function () {
            fetch('/api/tournaments/' + TID + '/cancel', { method: 'POST' })
                .then(function () { window.location.href = '/play/tournament'; });
        });

        document.getElementById('btn-start-trn')?.addEventListener('click', function () {
            this.disabled = true;
            this.textContent = T.started;
            fetch('/api/tournaments/' + TID + '/start', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.started) {
                        alert(data.detail || 'Error');
                    }
                });
        });

        document.getElementById('btn-trn-confirm-order')?.addEventListener('click', submitOrderingAnswer);

        connectWebSocket();

        if (STATUS === 'active' && currentRound > 0) {
            fetchStateAndLoadRound();
        } else if (STATUS === 'waiting') {
            showSection('trn-waiting');
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
                if (msg.rounds_config) roundsConfig = msg.rounds_config;
                // Show structure overview first
                showStructureOverview(function () {
                    showPreGame(currentRound, function () {
                        showSection('trn-game');
                        fetchStateAndLoadRound();
                    });
                });
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
                handleRoundFinished(msg);
                break;

            case 'tournament_finished':
                showFinalResults(msg.scoreboard, msg.player_usernames);
                break;

            case 'tournament_cancelled':
                showFeedback(T.cancelled, 'error');
                setTimeout(function () { window.location.href = '/play/tournament'; }, 1500);
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

    // ── Structure Overview ──────────────────────────────────
    function showStructureOverview(callback) {
        showSection('trn-structure-view');
        var list = document.getElementById('trn-structure-list');
        list.innerHTML = '';

        roundsConfig.forEach(function (rc, i) {
            var gameId = rc.game_id || 'ordering';
            var gameName = GAME_NAMES[gameId] || gameId;
            var contLabel = rc.continent === 'all' ? '' : ' · ' + rc.continent;
            var timerLabel = rc.timed ? ' ⏱' : '';

            var item = document.createElement('div');
            item.className = 'trn-struct-item' + (i === 0 ? ' active' : '');
            item.innerHTML =
                '<span class="trn-struct-num">' + (i + 1) + '</span>' +
                '<img src="' + (GAME_ICONS[gameId] || '') + '" width="32" height="32" alt="">' +
                '<div class="trn-struct-info">' +
                '  <strong>' + GeoFreak.escapeHtml(gameName) + '</strong>' +
                '  <small>' + (rc.num_questions || 10) + ' ' + T.questions + contLabel + timerLabel + '</small>' +
                '</div>';
            list.appendChild(item);
        });

        // Auto-proceed after 5 seconds
        setTimeout(callback, 5000);
    }

    // ── Pre-game Summary ────────────────────────────────────
    function showPreGame(roundNum, callback) {
        showSection('trn-pregame-view');
        var idx = roundNum - 1;
        var rc = roundsConfig[idx] || {};
        var gameId = rc.game_id || 'ordering';
        var gameName = GAME_NAMES[gameId] || gameId;

        document.getElementById('trn-pregame-img').src = GAME_ICONS[gameId] || '';
        document.getElementById('trn-pregame-title').textContent = gameName;

        var meta = document.getElementById('trn-pregame-meta');
        meta.innerHTML = '';
        var tags = [
            T.round_label + ' ' + roundNum + '/' + TOTAL_ROUNDS,
            (rc.num_questions || 10) + ' ' + T.questions,
        ];
        if (rc.continent && rc.continent !== 'all') tags.push(rc.continent);
        if (rc.timed) tags.push('⏱');
        tags.forEach(function (txt) {
            var span = document.createElement('span');
            span.className = 'trn-pregame-tag';
            span.textContent = txt;
            meta.appendChild(span);
        });

        // Show game instructions
        var instr = document.getElementById('trn-pregame-instr');
        if (window.GeoFreak && window.GeoFreak.GAME_INSTRUCTIONS && window.GeoFreak.GAME_INSTRUCTIONS[gameId]) {
            var gi = window.GeoFreak.GAME_INSTRUCTIONS[gameId];
            instr.innerHTML = '<p>' + GeoFreak.escapeHtml(gi.desc) + '</p>';
        } else {
            instr.innerHTML = '';
        }

        // Countdown 5→1
        var countdown = document.getElementById('trn-pregame-countdown');
        var count = 5;
        countdown.textContent = count;
        var iv = setInterval(function () {
            count--;
            if (count <= 0) {
                clearInterval(iv);
                callback();
            } else {
                countdown.textContent = count;
            }
        }, 1000);
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
                if (tourn.config && tourn.config.rounds) roundsConfig = tourn.config.rounds;
                updateScoreboard();
                loadRound(currentRound);
            });
    }

    function loadRound(roundNum) {
        showSection('trn-game');
        document.getElementById('trn-round-num').textContent = roundNum;
        document.getElementById('trn-round-total').textContent = TOTAL_ROUNDS;
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
                badge.textContent = GAME_NAMES[currentGameType] || currentGameType;

                document.getElementById('tq-total').textContent = questions.length;

                // Hide all game areas
                hideAllGameAreas();
                showQuestion();
            });
    }

    function hideAllGameAreas() {
        ['trn-ordering-items', 'trn-comparison-cards', 'trn-quiz-area', 'trn-geostats-area'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
        var btn = document.getElementById('btn-trn-confirm-order');
        if (btn) btn.style.display = 'none';
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
                '<span class="sb-name">' + GeoFreak.escapeHtml(e.name) + '</span>' +
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
        hideAllGameAreas();

        if (currentGameType === 'ordering') {
            document.getElementById('trn-ordering-items').style.display = 'flex';
            document.getElementById('btn-trn-confirm-order').style.display = 'inline-flex';
            document.getElementById('btn-trn-confirm-order').disabled = false;
            var label = q.stat_info[T.stat_label_key || 'label_es'] || q.stat;
            promptEl.innerHTML = (q.ascending ? T.prompt_asc : T.prompt_desc).replace('{stat}', label);
            renderOrderingItems(q.countries);
        } else if (currentGameType === 'comparison') {
            document.getElementById('trn-comparison-cards').style.display = 'flex';
            var label2 = q.stat_info[T.stat_label_key || 'label_es'] || q.stat;
            promptEl.innerHTML = (T.cmp_prompt || '').replace('{stat}', label2);
            renderComparisonCards(q.countries);
        } else if (currentGameType === 'flags' || currentGameType === 'outline') {
            document.getElementById('trn-quiz-area').style.display = 'block';
            promptEl.textContent = '';
            renderQuizQuestion(q);
        } else if (currentGameType === 'geostats') {
            document.getElementById('trn-geostats-area').style.display = 'block';
            promptEl.textContent = '';
            renderGeostatsQuestion(q);
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
                '<span class="ordering-name">' + GeoFreak.escapeHtml(co.name) + '</span>';
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
                '<span class="cmp-name">' + GeoFreak.escapeHtml(co.name) + '</span>';
            card.addEventListener('click', function () {
                c.querySelectorAll('.cmp-card').forEach(function (el) { el.style.pointerEvents = 'none'; });
                submitAnswer(co.iso_a3);
            });
            c.appendChild(card);
        });
    }

    // ── Quiz (flags/outline) ────────────────────────────────
    function renderQuizQuestion(q) {
        var display = document.getElementById('trn-quiz-display');
        var opts = document.getElementById('trn-quiz-options');

        if (currentGameType === 'flags') {
            // Show flag emoji large
            display.innerHTML = '<div style="font-size:5rem;margin-bottom:16px">' + (q.display.flag_emoji || '🏳️') + '</div>';
        } else {
            // Outline: show country outline (SVG silhouette via image)
            display.innerHTML = '<div style="font-size:5rem;margin-bottom:16px">🗺️</div>' +
                '<p style="color:var(--gray-500);font-size:.9rem">' + GeoFreak.escapeHtml(q.display.name || '') + '</p>';
        }

        opts.innerHTML = '';
        (q.options || []).forEach(function (o) {
            var btn = document.createElement('button');
            btn.className = 'trn-quiz-opt';
            btn.textContent = o.name || o.iso_a3;
            btn.addEventListener('click', function () {
                opts.querySelectorAll('.trn-quiz-opt').forEach(function (b) { b.disabled = true; });
                submitAnswer(o.iso_a3);
            });
            opts.appendChild(btn);
        });
    }

    // ── GeoStats ────────────────────────────────────────────
    function renderGeostatsQuestion(q) {
        var chartEl = document.getElementById('trn-gs-chart');
        var optsEl = document.getElementById('trn-gs-options');

        chartEl.innerHTML = '<p style="text-align:center;color:var(--gray-500);padding:20px">📈 GeoStats chart</p>';

        optsEl.innerHTML = '';
        (q.options || []).forEach(function (o) {
            var btn = document.createElement('button');
            btn.className = 'trn-quiz-opt';
            btn.textContent = o.name || o.iso_a3;
            btn.addEventListener('click', function () {
                optsEl.querySelectorAll('.trn-quiz-opt').forEach(function (b) { b.disabled = true; });
                submitAnswer(o.iso_a3);
            });
            optsEl.appendChild(btn);
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
            showFeedback(T.waiting_others, 'info');
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

    // ── Round finished → Global Scoreboard ──────────────────
    function handleRoundFinished(msg) {
        scoreboard = msg.scoreboard || scoreboard;
        roundScores[msg.round_number] = msg.round_scores || {};
        updateScoreboard();

        showGlobalScoreboard(msg.round_number, msg.next_round, msg.next_game_type);
    }

    function showGlobalScoreboard(finishedRound, nextRound, nextGameType) {
        showSection('trn-scoreboard-view');

        var remaining = TOTAL_ROUNDS - finishedRound;
        document.getElementById('trn-gsb-remaining').textContent =
            T.games_remaining + ': ' + remaining;

        // Build header
        var header = document.getElementById('trn-gsb-header');
        var headerHtml = '<th></th>';
        for (var r = 1; r <= finishedRound; r++) {
            headerHtml += '<th>R' + r + '</th>';
        }
        headerHtml += '<th>' + T.total_score + '</th>';
        header.innerHTML = headerHtml;

        // Build body
        var body = document.getElementById('trn-gsb-body');
        var entries = [];
        for (var uid in scoreboard) {
            entries.push({
                uid: uid,
                name: uid === USER_ID ? (T.you || 'You') : (playerUsernames[uid] || '?'),
                total: parseInt(scoreboard[uid] || 0, 10),
                isYou: uid === USER_ID
            });
        }
        entries.sort(function (a, b) { return b.total - a.total; });

        body.innerHTML = '';
        entries.forEach(function (e) {
            var row = '<tr class="' + (e.isYou ? 'is-you' : '') + '"><td>' + GeoFreak.escapeHtml(e.name) + '</td>';
            for (var r = 1; r <= finishedRound; r++) {
                var rs = roundScores[r] || {};
                row += '<td>' + parseInt(rs[e.uid] || 0, 10) + '</td>';
            }
            row += '<td>' + e.total + '</td></tr>';
            body.innerHTML += row;
        });

        var nextMsg = document.getElementById('trn-gsb-next');
        if (nextRound && nextGameType) {
            var nextName = GAME_NAMES[nextGameType] || nextGameType;
            nextMsg.textContent = T.next_game + ': ' + nextName;
            currentRound = nextRound;

            // After 5 seconds, show pre-game then load round
            setTimeout(function () {
                showPreGame(currentRound, function () {
                    showSection('trn-game');
                    loadRound(currentRound);
                });
            }, 5000);
        } else {
            nextMsg.textContent = '';
        }
    }

    // ── Final results ───────────────────────────────────────
    function showFinalResults(sb, usernames) {
        showSection('trn-results');

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
        if (myScore === topScore && myScore > 0) { icon.textContent = '🏆'; title.textContent = T.win; }
        else if (myScore === topScore) { icon.textContent = '🤝'; title.textContent = T.draw; }
        else { icon.textContent = '🎖️'; title.textContent = T.lose; }

        var medals = ['🥇', '🥈', '🥉'];
        var html = '';
        entries.forEach(function (e, i) {
            var medal = i < 3 ? medals[i] : (i + 1) + '.';
            html += '<div class="standing-row' + (e.uid === USER_ID ? ' is-you' : '') + '">' +
                '<span class="standing-medal">' + medal + '</span>' +
                '<span class="standing-name">' + GeoFreak.escapeHtml(e.name) + '</span>' +
                '<span class="standing-score">' + e.score + ' ' + T.points + '</span></div>';
        });
        document.getElementById('trn-final-standings').innerHTML = html;
    }

})();
