/* ============================================================
   GeoFreak — Tournament Designer Lobby
   ============================================================ */
(function () {
    var T = window.TRN_T || {};
    var CONT_NAMES = {all: T.all, europe: T.europe, asia: T.asia, africa: T.africa, america: T.america, oceania: T.oceania};

    // State
    var queue = [];  // [{game_id, game_name, game_color, game_icon, questions, rounds, continent, timed, secs_per_item}]
    var numPlayers = 2;
    var selectedGame = null;  // {id, name, color, icon, secs_per_item, type}

    // DOM refs
    var playerBtns = document.getElementById('trn-player-btns');
    var estTime = document.getElementById('trn-est-time');
    var picker = document.getElementById('trn-game-picker');
    var configPanel = document.getElementById('trn-config-panel');
    var queueEl = document.getElementById('trn-queue');
    var queueCount = document.getElementById('trn-queue-count');
    var emptyEl = document.getElementById('trn-queue-empty');
    var btnCreate = document.getElementById('btn-create-trn');
    var errorEl = document.getElementById('trn-create-error');

    // ── Player count ──────────────────────────────────────────
    if (playerBtns) {
        playerBtns.querySelectorAll('.trn-n-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                playerBtns.querySelectorAll('.trn-n-btn').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                numPlayers = parseInt(btn.getAttribute('data-n'), 10);
            });
        });
    }

    // ── N-button groups helper ──────────────────────────────
    function setupNBtns(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return;
        container.querySelectorAll('.trn-n-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                container.querySelectorAll('.trn-n-btn').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
            });
        });
    }

    // ── Game picker ───────────────────────────────────────────
    if (picker) {
        picker.querySelectorAll('.trn-pick-card').forEach(function (card) {
            card.addEventListener('click', function () {
                picker.querySelectorAll('.trn-pick-card').forEach(function (c) { c.classList.remove('selected'); });
                card.classList.add('selected');
                selectedGame = {
                    id: card.getAttribute('data-game-id'),
                    name: card.getAttribute('data-game-name'),
                    color: card.getAttribute('data-game-color'),
                    icon: card.getAttribute('data-game-icon'),
                    secs_per_item: parseInt(card.getAttribute('data-game-secs'), 10) || 20,
                    type: card.getAttribute('data-game-type')
                };
                // Show config panel
                document.getElementById('trn-cfg-icon').src = selectedGame.icon;
                document.getElementById('trn-cfg-name').textContent = selectedGame.name;
                configPanel.style.display = 'block';
                // Reset config to defaults
                resetConfig();
            });
        });
    }

    function resetConfig() {
        document.getElementById('trn-cfg-questions').value = '10';
        document.getElementById('trn-cfg-rounds').value = '1';
        document.getElementById('trn-cfg-continent').value = 'all';
        document.getElementById('trn-cfg-timer').checked = false;
    }

    // ── Info button ───────────────────────────────────────────
    var infoBtn = document.getElementById('trn-cfg-info');
    if (infoBtn) {
        infoBtn.addEventListener('click', function () {
            if (selectedGame && window.GeoFreak && window.GeoFreak.showGameInstructions) {
                window.GeoFreak.showGameInstructions(selectedGame.id);
            }
        });
    }

    // ── Add game to queue ─────────────────────────────────────
    var addBtn = document.getElementById('trn-cfg-add');
    if (addBtn) {
        addBtn.addEventListener('click', function () {
            if (!selectedGame) return;
            var totalRounds = queue.reduce(function (s, g) { return s + g.rounds; }, 0);
            var numQuestions = parseInt(document.getElementById('trn-cfg-questions').value, 10) || 10;
            var numRounds = parseInt(document.getElementById('trn-cfg-rounds').value, 10) || 1;

            if (totalRounds + numRounds > 10) {
                showError(T.max_games);
                return;
            }

            queue.push({
                game_id: selectedGame.id,
                game_name: selectedGame.name,
                game_color: selectedGame.color,
                game_icon: selectedGame.icon,
                questions: numQuestions,
                rounds: numRounds,
                continent: document.getElementById('trn-cfg-continent').value,
                timed: document.getElementById('trn-cfg-timer').checked,
                secs_per_item: selectedGame.secs_per_item
            });

            renderQueue();
            configPanel.style.display = 'none';
            picker.querySelectorAll('.trn-pick-card').forEach(function (c) { c.classList.remove('selected'); });
            selectedGame = null;
        });
    }

    // ── Render queue ──────────────────────────────────────────
    function renderQueue() {
        // Clear existing items
        var items = queueEl.querySelectorAll('.trn-queue-item');
        items.forEach(function (el) { el.remove(); });

        var totalRounds = queue.reduce(function (s, g) { return s + g.rounds; }, 0);
        queueCount.textContent = '(' + totalRounds + '/10)';
        emptyEl.style.display = queue.length === 0 ? 'block' : 'none';
        btnCreate.disabled = queue.length === 0;

        var roundIdx = 0;
        queue.forEach(function (game, idx) {
            for (var r = 0; r < game.rounds; r++) {
                roundIdx++;
                var item = document.createElement('div');
                item.className = 'trn-queue-item';
                item.style.cssText = '--card-color:' + game.game_color;

                var contLabel = CONT_NAMES[game.continent] || game.continent;
                var timerLabel = game.timed ? ' ⏱' : '';
                var roundLabel = game.rounds > 1 ? ' (' + (r + 1) + '/' + game.rounds + ')' : '';

                item.innerHTML =
                    '<div class="trn-qi-left">' +
                    '  <span class="trn-qi-num">' + roundIdx + '</span>' +
                    '  <img src="' + GeoFreak.escapeHtml(game.game_icon) + '" width="32" height="32" alt="">' +
                    '  <div class="trn-qi-info">' +
                    '    <strong>' + GeoFreak.escapeHtml(game.game_name) + roundLabel + '</strong>' +
                    '    <small>' + game.questions + ' ' + T.questions + ' · ' + contLabel + timerLabel + '</small>' +
                    '  </div>' +
                    '</div>' +
                    '<button class="trn-qi-remove" data-idx="' + idx + '" title="' + T.remove + '">&times;</button>';
                queueEl.appendChild(item);
            }
        });

        // Remove buttons (only once per game, on first round)
        queueEl.querySelectorAll('.trn-qi-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var i = parseInt(btn.getAttribute('data-idx'), 10);
                queue.splice(i, 1);
                renderQueue();
            });
        });

        updateEstTime();
    }

    // ── Estimated time ────────────────────────────────────────
    function updateEstTime() {
        var totalSecs = 0;
        var totalRounds = 0;
        queue.forEach(function (g) {
            for (var r = 0; r < g.rounds; r++) {
                totalRounds++;
                if (g.timed) {
                    totalSecs += g.questions * g.secs_per_item;
                } else {
                    totalSecs += g.questions * g.secs_per_item; // estimated even if not timed
                }
            }
        });
        totalSecs += totalRounds * 60; // 1 min overhead per game
        var mins = Math.ceil(totalSecs / 60);
        estTime.textContent = mins + ' ' + T.minutes;
    }

    // ── Create tournament ─────────────────────────────────────
    if (btnCreate) {
        btnCreate.addEventListener('click', function () {
            if (queue.length === 0) return;
            btnCreate.disabled = true;
            btnCreate.textContent = T.creating;
            hideError();

            // Build the games array to send
            var games = queue.map(function (g) {
                return {
                    game_id: g.game_id,
                    num_questions: g.questions,
                    rounds: g.rounds,
                    continent: g.continent,
                    timed: g.timed
                };
            });

            fetch('/api/tournaments/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    games: games,
                    num_players: numPlayers
                })
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.tournament_id) {
                    window.location.href = '/tournaments/' + data.tournament_id;
                } else {
                    showError(data.detail || 'Error');
                    btnCreate.disabled = false;
                    btnCreate.textContent = T.creating.replace('…', '');
                }
            })
            .catch(function () {
                btnCreate.disabled = false;
                btnCreate.textContent = T.creating.replace('…', '');
            });
        });
    }

    function showError(msg) {
        errorEl.textContent = msg;
        errorEl.style.display = 'block';
    }
    function hideError() { errorEl.style.display = 'none'; }
})();
