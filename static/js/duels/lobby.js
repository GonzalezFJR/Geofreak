/* ============================================================
   GeoFreak — Duel Lobby
   Creates duels and joins existing ones.
   ============================================================ */
(function () {
    var T = window.DUEL_TRANSLATIONS || {};
    var btnCreate = document.getElementById('btn-create-duel');
    var listEl = document.getElementById('duel-list');
    var loadingEl = document.getElementById('duel-list-loading');
    var emptyEl = document.getElementById('duel-list-empty');

    // ── Create duel ─────────────────────────────────────────
    if (btnCreate) {
        btnCreate.addEventListener('click', function () {
            var gameType = document.getElementById('duel-game-type').value;
            var continent = document.getElementById('duel-continent').value;
            var numQ = parseInt(document.getElementById('duel-num-questions').value, 10);
            btnCreate.disabled = true;
            btnCreate.textContent = T.creating || 'Creating…';

            fetch('/api/duels/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    game_type: gameType,
                    num_questions: numQ,
                    continent: continent
                })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.duel_id) {
                        window.location.href = '/duels/' + data.duel_id;
                    } else {
                        alert(data.detail || 'Error');
                        btnCreate.disabled = false;
                        btnCreate.textContent = T.creating ? T.creating.replace('…', '') : 'Create';
                    }
                })
                .catch(function () {
                    btnCreate.disabled = false;
                    btnCreate.textContent = T.creating ? T.creating.replace('…', '') : 'Create';
                });
        });
    }

    // ── Load waiting duels ──────────────────────────────────
    function loadDuels() {
        if (loadingEl) loadingEl.style.display = 'block';
        if (emptyEl) emptyEl.style.display = 'none';

        fetch('/api/duels/waiting')
            .then(function (r) { return r.json(); })
            .then(function (duels) {
                if (loadingEl) loadingEl.style.display = 'none';
                renderDuels(duels);
            })
            .catch(function () {
                if (loadingEl) loadingEl.style.display = 'none';
            });
    }

    function renderDuels(duels) {
        // Remove old cards
        var old = listEl.querySelectorAll('.duel-card');
        for (var i = 0; i < old.length; i++) old[i].remove();

        if (duels.length === 0) {
            if (emptyEl) emptyEl.style.display = 'block';
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        duels.forEach(function (d) {
            var card = document.createElement('div');
            card.className = 'duel-card';
            var gameLabel = d.game_type === 'ordering' ? (T.ordering || 'Ordering') : (T.comparison || 'Comparison');
            card.innerHTML =
                '<div class="duel-card-info">' +
                '<span class="duel-card-type">' + gameLabel + '</span>' +
                '<span class="duel-card-meta">' + (d.num_questions || 10) + ' ' + (T.questions || 'questions') + '</span>' +
                '<span class="duel-card-creator">' + (T.by || 'by') + ' ' + GeoFreak.escapeHtml(d.creator_username || '?') + '</span>' +
                '</div>' +
                '<button class="btn btn-primary btn-join" data-id="' + d.duel_id + '">' + (T.join || 'Join') + '</button>';
            listEl.appendChild(card);
        });

        // Bind join buttons
        listEl.querySelectorAll('.btn-join').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var duelId = this.getAttribute('data-id');
                this.disabled = true;
                this.textContent = T.joining || 'Joining…';
                fetch('/api/duels/' + duelId + '/join', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.duel_id) {
                            window.location.href = '/duels/' + data.duel_id;
                        } else {
                            alert(data.detail || 'Error');
                            loadDuels();
                        }
                    })
                    .catch(function () { loadDuels(); });
            });
        });
    }

    loadDuels();
    // Refresh every 5 seconds
    setInterval(loadDuels, 5000);
})();
