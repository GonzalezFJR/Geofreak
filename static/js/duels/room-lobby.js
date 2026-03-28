/* GeoFreak — Room Lobby JS
   Handles Create/Join logic for the room lobby page.
   Guest ID stored in localStorage under 'gf_guest_id'.
*/
(function () {
    'use strict';

    // ── Guest ID ───────────────────────────────────────────────────────────────
    function getGuestId() {
        var id = localStorage.getItem('gf_guest_id');
        if (!id) {
            id = 'g_' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
            id = id.slice(0, 40);
            localStorage.setItem('gf_guest_id', id);
        }
        return id;
    }

    // ── Dataset selector: hide continent when non-countries ───────────────────
    var _datasetSel = document.getElementById('create-dataset');
    if (_datasetSel) {
        _datasetSel.addEventListener('change', function () {
            var row = document.getElementById('create-continent-row');
            if (row) row.style.display = this.value === 'countries' ? '' : 'none';
        });
    }

    // ── N-items buttons ────────────────────────────────────────────────────────
    document.querySelectorAll('#create-n-btns .room-n-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#create-n-btns .room-n-btn').forEach(function (b) {
                b.classList.remove('active');
            });
            btn.classList.add('active');
            document.getElementById('create-n').value = btn.getAttribute('data-n');
        });
    });

    // ── Helpers ────────────────────────────────────────────────────────────────
    function showError(elId, msg) {
        var el = document.getElementById(elId);
        if (el) { el.textContent = msg; el.style.display = ''; }
    }
    function hideError(elId) {
        var el = document.getElementById(elId);
        if (el) { el.style.display = 'none'; el.textContent = ''; }
    }
    function setLoading(btnId, loading, originalText) {
        var btn = document.getElementById(btnId);
        if (!btn) return;
        btn.disabled = loading;
        btn.textContent = loading ? '…' : originalText;
    }

    // ── Create ────────────────────────────────────────────────────────────────
    window.RoomLobby = {
        create: function () {
            hideError('create-error');
            var nItems = parseInt(document.getElementById('create-n').value) || 10;
            var difficulty = document.getElementById('create-difficulty').value;
            var dataset = (document.getElementById('create-dataset') || {}).value || 'countries';
            var continent = (document.getElementById('create-continent') || {}).value || 'all';
            var body = {
                game_id: ROOM_GAME_ID,
                n_items: nItems,
                difficulty: difficulty,
                countdown: true,
                dataset: dataset,
                continent: dataset === 'countries' ? continent : 'all',
            };
            if (!ROOM_IS_LOGGED) {
                var name = (document.getElementById('create-guest-name') || {}).value || '';
                name = name.trim();
                if (!name) { showError('create-error', ROOM_T.err_name); return; }
                body.guest_id = getGuestId();
                body.guest_name = name;
            }

            var btn = document.getElementById('btn-create');
            btn.disabled = true;
            btn.textContent = ROOM_T.creating;

            fetch('/api/rooms/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (res) {
                    if (!res.ok) {
                        btn.disabled = false;
                        btn.textContent = btn.getAttribute('data-orig') || 'Crear';
                        var msg = res.data.detail || ROOM_T.err_generic;
                        showError('create-error', msg);
                        return;
                    }
                    var code = res.data.code;
                    var playerId = res.data.player_id;
                    // Store in localStorage
                    localStorage.setItem('gf_room_code', code);
                    localStorage.setItem('gf_room_player_id', playerId);
                    localStorage.setItem('gf_room_game_id', ROOM_GAME_ID);
                    // Show code display
                    document.getElementById('create-settings').style.display = 'none';
                    var codeDisplay = document.getElementById('create-code-display');
                    codeDisplay.style.display = '';
                    document.getElementById('created-code').textContent = code;
                    var goBtn = document.getElementById('btn-go-room');
                    goBtn.href = '/duel/' + ROOM_GAME_ID + '/room/' + code;
                })
                .catch(function () {
                    btn.disabled = false;
                    showError('create-error', ROOM_T.err_generic);
                });
        },

        join: function () {
            hideError('join-error');
            var code = (document.getElementById('join-code').value || '').trim().toUpperCase();
            if (code.length !== 8) { showError('join-error', ROOM_T.err_code); return; }

            var body = {};
            if (!ROOM_IS_LOGGED) {
                var name = (document.getElementById('join-guest-name') || {}).value || '';
                name = name.trim();
                if (!name) { showError('join-error', ROOM_T.err_name); return; }
                body.guest_id = getGuestId();
                body.guest_name = name;
            }

            var btn = document.getElementById('btn-join');
            btn.disabled = true;
            btn.textContent = ROOM_T.joining;

            fetch('/api/rooms/' + code + '/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (res) {
                    if (!res.ok) {
                        btn.disabled = false;
                        btn.textContent = ROOM_T.join_btn || 'Unirse';
                        var detail = res.data.detail || '';
                        var msg = {
                            room_not_found: ROOM_T.err_not_found,
                            already_started: ROOM_T.err_started,
                            room_full: ROOM_T.err_full,
                        }[detail] || ROOM_T.err_generic;
                        showError('join-error', msg);
                        return;
                    }
                    var gameId = res.data.game_id || ROOM_GAME_ID;
                    var playerId = res.data.player_id;
                    localStorage.setItem('gf_room_code', code);
                    localStorage.setItem('gf_room_player_id', playerId);
                    localStorage.setItem('gf_room_game_id', gameId);
                    window.location.href = '/duel/' + gameId + '/room/' + code;
                })
                .catch(function () {
                    btn.disabled = false;
                    showError('join-error', ROOM_T.err_generic);
                });
        },

        switchTab: function (tab) {
            var isCreate = tab === 'create';
            document.getElementById('panel-create').style.display = isCreate ? '' : 'none';
            document.getElementById('panel-join').style.display = isCreate ? 'none' : '';
            document.getElementById('tab-create').classList.toggle('active', isCreate);
            document.getElementById('tab-join').classList.toggle('active', !isCreate);
        },

        copyCode: function () {
            var code = (document.getElementById('created-code') || {}).textContent || '';
            if (!code || code === '–') return;
            var btn = document.querySelector('.room-copy-btn');
            if (navigator.clipboard) {
                navigator.clipboard.writeText(code).then(function () {
                    if (btn) { btn.textContent = ROOM_T.copied; setTimeout(function () { btn.textContent = 'Copiar'; }, 1500); }
                });
            }
        },
    };
}());
