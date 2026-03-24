/* ============================================================
   GeoFreak — Tournament Lobby
   ============================================================ */
(function () {
    var T = window.TRN_T || {};
    var btnCreate = document.getElementById('btn-create-trn');
    var listEl = document.getElementById('trn-list');
    var emptyEl = document.getElementById('trn-list-empty');

    if (btnCreate) {
        btnCreate.addEventListener('click', function () {
            var rounds = parseInt(document.getElementById('trn-rounds').value, 10);
            var questions = parseInt(document.getElementById('trn-questions').value, 10);
            var continent = document.getElementById('trn-continent').value;
            var gameTypes = [];
            if (document.getElementById('trn-type-ordering').checked) gameTypes.push('ordering');
            if (document.getElementById('trn-type-comparison').checked) gameTypes.push('comparison');
            if (gameTypes.length === 0) gameTypes = ['ordering', 'comparison'];

            btnCreate.disabled = true;
            btnCreate.textContent = T.creating || 'Creating…';

            fetch('/api/tournaments/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    number_of_rounds: rounds,
                    num_questions: questions,
                    continent: continent,
                    game_types: gameTypes
                })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.tournament_id) {
                        window.location.href = '/tournaments/' + data.tournament_id;
                    } else {
                        alert(data.detail || 'Error');
                        btnCreate.disabled = false;
                        btnCreate.textContent = T.creating ? T.creating.replace('…', '') : 'Create';
                    }
                })
                .catch(function () {
                    btnCreate.disabled = false;
                });
        });
    }

    function loadTournaments() {
        if (emptyEl) emptyEl.style.display = 'none';
        fetch('/api/tournaments/waiting')
            .then(function (r) { return r.json(); })
            .then(function (items) { renderList(items); })
            .catch(function () {});
    }

    function renderList(items) {
        var old = listEl.querySelectorAll('.trn-card');
        for (var i = 0; i < old.length; i++) old[i].remove();

        if (items.length === 0) {
            if (emptyEl) emptyEl.style.display = 'block';
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';

        items.forEach(function (t) {
            var card = document.createElement('div');
            card.className = 'trn-card';
            card.innerHTML =
                '<div class="trn-card-info">' +
                '<span class="trn-card-rounds">' + t.number_of_rounds + ' ' + (T.rounds || 'rounds') + '</span>' +
                '<span class="trn-card-meta">' + (t.player_count || 1) + ' ' + (T.players || 'players') + '</span>' +
                '<span class="trn-card-creator">' + (T.by || 'by') + ' ' + GeoFreak.escapeHtml(t.creator_username || '?') + '</span>' +
                '</div>' +
                '<button class="btn btn-primary btn-join" data-id="' + t.tournament_id + '">' + (T.join || 'Join') + '</button>';
            listEl.appendChild(card);
        });

        listEl.querySelectorAll('.btn-join').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var id = this.getAttribute('data-id');
                this.disabled = true;
                this.textContent = T.joining || 'Joining…';
                fetch('/api/tournaments/' + id + '/join', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.tournament_id) window.location.href = '/tournaments/' + data.tournament_id;
                        else { alert(data.detail || 'Error'); loadTournaments(); }
                    })
                    .catch(function () { loadTournaments(); });
            });
        });
    }

    loadTournaments();
    setInterval(loadTournaments, 5000);
})();
