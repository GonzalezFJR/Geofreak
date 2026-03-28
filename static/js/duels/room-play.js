/* GeoFreak — Room Play JS
   Handles the room play page: lobby polling → game → results.
   Supports: comparison, ordering, geostats game types.
*/
(function () {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────────────
    var state = {
        roomCode: ROOM_CODE,
        gameId: ROOM_GAME_ID,
        playerId: '',
        isHost: false,
        roomStatus: 'lobby',
        questions: [],
        config: {},
        qIndex: 0,
        score: 0,
        startTime: 0,
        timer: null,
        timerInterval: null,
        pollInterval: null,
        geoGuessPos: null,   // 0-1 fraction for geostats
        ordSelected: null,   // index of selected card for swap
    };

    // ── Init ──────────────────────────────────────────────────────────────────
    function init() {
        // Recover player identity from localStorage
        var storedCode = localStorage.getItem('gf_room_code');
        var storedId   = localStorage.getItem('gf_room_player_id');
        if (storedCode === ROOM_CODE && storedId) {
            state.playerId = storedId;
        } else if (ROOM_IS_LOGGED && ROOM_USER_ID) {
            state.playerId = ROOM_USER_ID;
        } else {
            // Guest without localStorage (direct navigation) — use guest_id if exists
            var gid = localStorage.getItem('gf_guest_id');
            state.playerId = gid || '';
        }
        startPolling(3000);
    }

    // ── Polling ────────────────────────────────────────────────────────────────
    function startPolling(ms) {
        pollOnce();
        state.pollInterval = setInterval(pollOnce, ms);
    }

    function stopPolling() {
        if (state.pollInterval) { clearInterval(state.pollInterval); state.pollInterval = null; }
    }

    function pollOnce() {
        fetch('/api/rooms/' + state.roomCode + '/state')
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data) return;
                handleRoomState(data);
            })
            .catch(function () {});
    }

    function handleRoomState(data) {
        var prevStatus = state.roomStatus;
        state.roomStatus = data.status;
        state.config = data.config || {};
        state.isHost = (data.host_player_id === state.playerId);

        if (data.status === 'lobby') {
            renderLobby(data);
        } else if (data.status === 'playing' && prevStatus === 'lobby') {
            stopPolling();
            showSection('rp-game');
            loadAndStartGame();
        } else if (data.status === 'playing') {
            // Already in game — do nothing (game loop handles itself)
        } else if (data.status === 'finished') {
            stopPolling();
            showResults(data);
        }
    }

    // ── Lobby rendering ────────────────────────────────────────────────────────
    function renderLobby(data) {
        showSection('rp-lobby');

        // Player count
        var players = data.players || [];
        var countEl = document.getElementById('rp-player-count');
        if (countEl) countEl.textContent = players.length;

        // Player list
        var list = document.getElementById('rp-players-list');
        if (list) {
            list.innerHTML = '';
            players.forEach(function (p) {
                var li = document.createElement('li');
                li.className = 'rp-player-item';
                var isYou = (p.player_id === state.playerId);
                var isHost = (p.player_id === data.host_player_id);
                li.innerHTML =
                    '<span class="rp-player-name">' + esc(p.name) + '</span>' +
                    (isHost ? '<span class="rp-player-badge rp-badge-host">' + ROOM_T.host + '</span>' : '') +
                    (isYou  ? '<span class="rp-player-badge rp-badge-you">'  + ROOM_T.you  + '</span>' : '') +
                    (p.is_guest ? '<span class="rp-player-badge rp-badge-guest">👤</span>' : '');
                list.appendChild(li);
            });
        }

        // Config summary
        var cfgEl = document.getElementById('rp-config-summary');
        if (cfgEl) {
            var cfg = data.config || {};
            var diffKey = 'diff_' + (cfg.difficulty || 'normal');
            var diffLabel = ROOM_T[diffKey] || cfg.difficulty || 'normal';
            cfgEl.innerHTML =
                '<span>' + ROOM_T.cfg_items + ': <b>' + (cfg.n_items || '?') + '</b></span>' +
                '<span>' + ROOM_T.cfg_difficulty + ': <b>' + diffLabel + '</b></span>';
        }

        // Start / Wait buttons
        var startArea = document.getElementById('rp-start-area');
        var waitHost  = document.getElementById('rp-wait-host');
        if (state.isHost) {
            if (startArea) startArea.style.display = '';
            if (waitHost)  waitHost.style.display = 'none';
        } else {
            if (startArea) startArea.style.display = 'none';
            if (waitHost)  waitHost.style.display = '';
        }
    }

    // ── Start game ────────────────────────────────────────────────────────────
    window.RoomPlay = {
        start: function () {
            var btn = document.getElementById('btn-start');
            if (btn) { btn.disabled = true; btn.textContent = ROOM_T.starting; }
            hideError('rp-start-error');

            fetch('/api/rooms/' + state.roomCode + '/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ player_id: state.playerId }),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (res) {
                    if (!res.ok) {
                        if (btn) { btn.disabled = false; btn.textContent = '▶ ' + (ROOM_T.start_btn || 'Comenzar'); }
                        showError('rp-start-error', ROOM_T.err_start);
                    }
                    // Poll will detect status change and start game
                })
                .catch(function () {
                    if (btn) btn.disabled = false;
                    showError('rp-start-error', ROOM_T.err_start);
                });
        },

        copyCode: function () {
            var code = ROOM_CODE;
            var btn = document.querySelector('.rp-code-box .room-copy-btn');
            if (navigator.clipboard) {
                navigator.clipboard.writeText(code).then(function () {
                    if (btn) { var orig = btn.textContent; btn.textContent = ROOM_T.copied; setTimeout(function () { btn.textContent = orig; }, 1500); }
                });
            }
        },

        // ── Ordering ────────────────────────────────────────────────────────────
        ordClick: function (idx) {
            var items = document.querySelectorAll('.rp-ord-item');
            if (state.ordSelected === null) {
                state.ordSelected = idx;
                items[idx].classList.add('rp-selected');
            } else if (state.ordSelected === idx) {
                state.ordSelected = null;
                items[idx].classList.remove('rp-selected');
            } else {
                // Swap
                var a = state.ordSelected, b = idx;
                items[a].classList.remove('rp-selected');
                state.ordSelected = null;
                swapOrdItems(a, b);
            }
        },

        confirmOrder: function () {
            var q = state.questions[state.qIndex];
            if (!q) return;
            document.getElementById('rp-ord-confirm').style.display = 'none';
            var items = document.querySelectorAll('.rp-ord-item');
            var submitted = Array.from(items).map(function (el) { return el.getAttribute('data-iso'); });
            var correct = q.correct_order || [];
            var isCorrect = JSON.stringify(submitted) === JSON.stringify(correct);
            if (isCorrect) state.score++;
            updateHud();

            // Show feedback with correct order + values
            var fbEl = document.getElementById('rp-ord-fb');
            if (fbEl) {
                var lang = CURRENT_LANG;
                fbEl.innerHTML = (isCorrect ? '<span class="fb-correct">' + ROOM_T.correct + '</span>' : '<span class="fb-wrong">' + ROOM_T.wrong + '</span>') +
                    '<div class="rp-ord-solution">' +
                    correct.map(function (iso, i) {
                        var c = q.countries.find(function (x) { return x.iso_a3 === iso; });
                        var name = c ? (c['name_' + lang] || c.name) : iso;
                        var val = q.correct_values ? q.correct_values[iso] : '';
                        var formatted = val !== undefined && val !== '' ? formatVal(val, q.stat_info) : '';
                        return '<div class="rp-ord-sol-item' + (submitted[i] === iso ? '' : ' rp-sol-mismatch') + '">' +
                            '<span class="rp-ord-sol-rank">' + (i + 1) + '</span>' +
                            '<span class="rp-ord-sol-flag">' + (c ? c.flag_emoji : '') + '</span>' +
                            '<span class="rp-ord-sol-name">' + esc(name) + '</span>' +
                            (formatted ? '<span class="rp-ord-sol-val">' + formatted + '</span>' : '') +
                            '</div>';
                    }).join('') +
                    '</div>';
                fbEl.style.display = '';
            }
            document.getElementById('rp-ord-next').style.display = '';
        },

        // ── Geostats ─────────────────────────────────────────────────────────────
        geoClick: function (e) {
            var curve = document.getElementById('rp-geo-curve');
            if (!curve) return;
            var rect = curve.getBoundingClientRect();
            var pos = (e.clientX - rect.left) / rect.width;
            pos = Math.max(0, Math.min(1, pos));
            state.geoGuessPos = pos;
            // Update guess marker
            var marker = document.getElementById('rp-geo-guess-marker');
            if (marker) {
                marker.style.left = (pos * 100) + '%';
                marker.style.display = '';
            }
            document.getElementById('rp-geo-confirm').style.display = '';
        },

        confirmGeo: function () {
            var q = state.questions[state.qIndex];
            if (!q || state.geoGuessPos === null) return;
            document.getElementById('rp-geo-confirm').style.display = 'none';

            var total = (q.curve || []).length;
            var targetIdx = q.target_index || 0;
            var targetPos = total > 1 ? targetIdx / (total - 1) : 0.5;
            var guessPos = state.geoGuessPos;
            var tolerance = 0.15; // 15% of curve = correct
            var dist = Math.abs(guessPos - targetPos);
            var isCorrect = dist <= tolerance;
            if (isCorrect) state.score++;
            updateHud();

            // Show correct marker
            var correctMarker = document.getElementById('rp-geo-correct-marker');
            if (correctMarker) {
                correctMarker.style.left = (targetPos * 100) + '%';
                correctMarker.style.display = '';
            }

            // Feedback
            var fbEl = document.getElementById('rp-geo-fb');
            if (fbEl) {
                var lang = CURRENT_LANG;
                var target = q.target_iso || '';
                // Find country name from curve positions
                var countries = q.countries_lookup || {};
                var cData = countries[target] || {};
                var cName = cData['name_' + lang] || cData.name || target;
                var cFlag = cData.flag_emoji || '';
                var cVal = q.curve ? q.curve[targetIdx] : '';
                fbEl.innerHTML =
                    (isCorrect ? '<span class="fb-correct">' + ROOM_T.geo_correct + '</span>' :
                     dist <= 0.3 ? '<span class="fb-partial">' + ROOM_T.geo_close + '</span>' :
                                   '<span class="fb-wrong">' + ROOM_T.geo_wrong + '</span>') +
                    '<div class="rp-geo-answer">' + cFlag + ' ' + esc(cName) + ' — ' + formatVal(cVal, q.stat_info) + '</div>';
                fbEl.style.display = '';
            }
            document.getElementById('rp-geo-next').style.display = '';
            // Disable further clicking
            document.getElementById('rp-geo-curve').style.pointerEvents = 'none';
        },

        nextQuestion: function () {
            state.qIndex++;
            if (state.qIndex >= state.questions.length) {
                finishGame();
            } else {
                renderQuestion();
            }
        },
    };

    // ── Load questions & start game ────────────────────────────────────────────
    function loadAndStartGame() {
        fetch('/api/rooms/' + state.roomCode + '/questions?player_id=' + encodeURIComponent(state.playerId))
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                if (!data || !data.questions || !data.questions.length) {
                    // Retry once after short delay
                    setTimeout(loadAndStartGame, 1500);
                    return;
                }
                state.questions = data.questions;
                state.config = data.config || {};
                state.qIndex = 0;
                state.score = 0;
                state.startTime = Date.now();
                setupHud();
                renderQuestion();
                if (state.config.countdown) startCountdown();
            })
            .catch(function () { setTimeout(loadAndStartGame, 2000); });
    }

    // ── HUD ────────────────────────────────────────────────────────────────────
    function setupHud() {
        var totalEl = document.getElementById('rp-q-total');
        if (totalEl) totalEl.textContent = state.questions.length;
        updateHud();
    }

    function updateHud() {
        var numEl = document.getElementById('rp-q-num');
        if (numEl) numEl.textContent = state.qIndex + 1;
        var scoreEl = document.getElementById('rp-score');
        if (scoreEl) scoreEl.textContent = state.score;
    }

    function startCountdown() {
        var cfg = state.config;
        var secs = ((cfg.n_items || state.questions.length) * 20);
        var endTime = Date.now() + secs * 1000;
        var timerEl = document.getElementById('rp-timer');
        var valEl   = document.getElementById('rp-timer-val');
        if (timerEl) timerEl.style.display = '';
        state.timerInterval = setInterval(function () {
            var rem = Math.max(0, Math.ceil((endTime - Date.now()) / 1000));
            var m = Math.floor(rem / 60), s = rem % 60;
            if (valEl) valEl.textContent = m + ':' + (s < 10 ? '0' : '') + s;
            if (rem <= 0) {
                clearInterval(state.timerInterval);
                finishGame();
            }
        }, 500);
    }

    // ── Question rendering ─────────────────────────────────────────────────────
    function renderQuestion() {
        updateHud();
        var q = state.questions[state.qIndex];
        if (!q) { finishGame(); return; }

        var gameType = ROOM_GAME_ID;
        // Hide all game panels
        ['rp-cmp', 'rp-ord', 'rp-geo'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });

        if (gameType === 'comparison') {
            renderComparison(q);
        } else if (gameType === 'ordering') {
            renderOrdering(q);
        } else if (gameType === 'geostats') {
            renderGeostats(q);
        }
    }

    // ── Comparison ─────────────────────────────────────────────────────────────
    function renderComparison(q) {
        var panel = document.getElementById('rp-cmp');
        if (!panel) return;
        panel.style.display = '';

        var lang = CURRENT_LANG;
        var statLabel = q.stat_info ? (q.stat_info['label_' + lang] || q.stat_info.label_en || q.stat) : q.stat;
        var promptEl = document.getElementById('rp-cmp-prompt');
        if (promptEl) promptEl.innerHTML = ROOM_T.cmp_prompt.replace('{stat}', '<em>' + esc(statLabel) + '</em>');

        var cardsEl = document.getElementById('rp-cmp-cards');
        if (cardsEl) {
            cardsEl.innerHTML = '';
            q.countries.forEach(function (c) {
                var btn = document.createElement('button');
                btn.className = 'rp-cmp-card';
                btn.setAttribute('data-iso', c.iso_a3);
                var cName = c['name_' + lang] || c.name;
                btn.innerHTML =
                    '<span class="rp-cmp-flag">' + (c.flag_emoji || '') + '</span>' +
                    '<span class="rp-cmp-name">' + esc(cName) + '</span>';
                btn.addEventListener('click', function () { handleCmpClick(q, c.iso_a3); });
                cardsEl.appendChild(btn);
            });
        }
        var fbEl = document.getElementById('rp-cmp-fb');
        if (fbEl) { fbEl.innerHTML = ''; fbEl.style.display = 'none'; }
    }

    function handleCmpClick(q, chosenIso) {
        // Disable all cards
        document.querySelectorAll('.rp-cmp-card').forEach(function (btn) { btn.disabled = true; });

        var isCorrect = (chosenIso === q.correct_iso);
        if (isCorrect) state.score++;
        updateHud();

        // Show feedback on cards
        var lang = CURRENT_LANG;
        document.querySelectorAll('.rp-cmp-card').forEach(function (btn) {
            var iso = btn.getAttribute('data-iso');
            var val = q.values ? q.values[iso] : undefined;
            var valFmt = val !== undefined ? formatVal(val, q.stat_info) : '';
            if (valFmt) btn.innerHTML += '<span class="rp-cmp-val">' + valFmt + '</span>';
            if (iso === q.correct_iso) btn.classList.add('rp-card-correct');
            else if (iso === chosenIso) btn.classList.add('rp-card-wrong');
        });

        var fbEl = document.getElementById('rp-cmp-fb');
        if (fbEl) {
            fbEl.innerHTML = isCorrect ?
                '<span class="fb-correct">' + ROOM_T.correct + '</span>' :
                '<span class="fb-wrong">' + ROOM_T.wrong + '</span>';
            fbEl.style.display = '';
        }

        setTimeout(function () { RoomPlay.nextQuestion(); }, 1200);
    }

    // ── Ordering ───────────────────────────────────────────────────────────────
    function renderOrdering(q) {
        var panel = document.getElementById('rp-ord');
        if (!panel) return;
        panel.style.display = '';
        state.ordSelected = null;

        var lang = CURRENT_LANG;
        var statLabel = q.stat_info ? (q.stat_info['label_' + lang] || q.stat_info.label_en || q.stat) : q.stat;
        var promptEl = document.getElementById('rp-ord-prompt');
        if (promptEl) {
            var tpl = q.ascending ? ROOM_T.ord_asc : ROOM_T.ord_desc;
            promptEl.innerHTML = tpl.replace('{stat}', '<em>' + esc(statLabel) + '</em>');
        }

        var list = document.getElementById('rp-ord-list');
        if (list) {
            list.innerHTML = '';
            q.countries.forEach(function (c, i) {
                var li = document.createElement('li');
                li.className = 'rp-ord-item';
                li.setAttribute('data-iso', c.iso_a3);
                li.setAttribute('data-idx', i);
                var cName = c['name_' + lang] || c.name;
                li.innerHTML =
                    '<span class="rp-ord-handle">☰</span>' +
                    '<span class="rp-ord-flag">' + (c.flag_emoji || '') + '</span>' +
                    '<span class="rp-ord-name">' + esc(cName) + '</span>';
                li.addEventListener('click', function () { RoomPlay.ordClick(i); });
                list.appendChild(li);
            });
        }

        var confirmBtn = document.getElementById('rp-ord-confirm');
        if (confirmBtn) confirmBtn.style.display = '';
        var fbEl = document.getElementById('rp-ord-fb');
        if (fbEl) { fbEl.innerHTML = ''; fbEl.style.display = 'none'; }
        var nextBtn = document.getElementById('rp-ord-next');
        if (nextBtn) nextBtn.style.display = 'none';
    }

    function swapOrdItems(a, b) {
        var list = document.getElementById('rp-ord-list');
        if (!list) return;
        var items = Array.from(list.querySelectorAll('.rp-ord-item'));
        var aEl = items[a], bEl = items[b];
        if (!aEl || !bEl) return;
        // Swap in DOM
        var aNext = aEl.nextSibling;
        list.insertBefore(aEl, bEl);
        list.insertBefore(bEl, aNext);
        // Re-assign click handlers with updated indices
        var newItems = Array.from(list.querySelectorAll('.rp-ord-item'));
        newItems.forEach(function (el, i) {
            el.setAttribute('data-idx', i);
            el.onclick = function () { RoomPlay.ordClick(i); };
        });
    }

    // ── Geostats ──────────────────────────────────────────────────────────────
    function renderGeostats(q) {
        var panel = document.getElementById('rp-geo');
        if (!panel) return;
        panel.style.display = '';
        state.geoGuessPos = null;

        var lang = CURRENT_LANG;
        var statLabel = q.stat_info ? (q.stat_info['label_' + lang] || q.stat_info.label_en || q.stat) : q.stat;
        var unit = q.stat_info ? (q.stat_info.unit || '') : '';

        // Prompt — we show the country name and ask where it ranks
        var target = q.target_iso || '';
        var countries_lookup = q.countries_lookup || {};
        // Note: for room mode geostats questions include countries_lookup inline
        var cData = countries_lookup[target] || {};
        var cName = cData['name_' + lang] || cData.name || target;
        var cFlag = cData.flag_emoji || '';

        var promptEl = document.getElementById('rp-geo-prompt');
        if (promptEl) promptEl.innerHTML = ROOM_T.geo_prompt.replace('{stat}', '<em>' + esc(statLabel) + '</em>');

        var targetEl = document.getElementById('rp-geo-target');
        if (targetEl) targetEl.innerHTML = '<span class="rp-geo-flag">' + cFlag + '</span> <span class="rp-geo-cname">' + esc(cName) + '</span>';

        // Min/max labels
        var curve = q.curve || [];
        var minEl = document.getElementById('rp-geo-min');
        var maxEl = document.getElementById('rp-geo-max');
        if (minEl && curve.length > 0) minEl.textContent = formatVal(curve[0], q.stat_info);
        if (maxEl && curve.length > 0) maxEl.textContent = formatVal(curve[curve.length - 1], q.stat_info);

        // Reset markers and curve
        var guessMarker = document.getElementById('rp-geo-guess-marker');
        var correctMarker = document.getElementById('rp-geo-correct-marker');
        var curve_el = document.getElementById('rp-geo-curve');
        if (guessMarker) guessMarker.style.display = 'none';
        if (correctMarker) correctMarker.style.display = 'none';
        if (curve_el) curve_el.style.pointerEvents = '';

        var confirmBtn = document.getElementById('rp-geo-confirm');
        if (confirmBtn) confirmBtn.style.display = 'none';
        var fbEl = document.getElementById('rp-geo-fb');
        if (fbEl) { fbEl.innerHTML = ''; fbEl.style.display = 'none'; }
        var nextBtn = document.getElementById('rp-geo-next');
        if (nextBtn) nextBtn.style.display = 'none';
    }

    // ── Finish game ───────────────────────────────────────────────────────────
    function finishGame() {
        if (state.timerInterval) { clearInterval(state.timerInterval); state.timerInterval = null; }
        var timeMs = Date.now() - state.startTime;
        var total  = state.questions.length;

        fetch('/api/rooms/' + state.roomCode + '/score', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                player_id: state.playerId,
                score: state.score,
                total: total,
                time_ms: timeMs,
            }),
        }).catch(function () {});

        // Show waiting-for-results section, poll for leaderboard
        showSection('rp-waiting-results');
        startPolling(4000);
    }

    // ── Results ────────────────────────────────────────────────────────────────
    function showResults(data) {
        showSection('rp-results');
        var scores  = data.scores || {};
        var players = data.players || [];

        // Build sorted list
        var ranked = players.map(function (p) {
            var s = scores[p.player_id] || {};
            return { name: p.name, player_id: p.player_id, score: s.score || 0, pct: s.pct || 0, time_ms: s.time_ms || 0 };
        });
        ranked.sort(function (a, b) { return b.score - a.score || a.time_ms - b.time_ms; });

        var lb = document.getElementById('rp-leaderboard');
        if (lb) {
            lb.innerHTML = '';
            ranked.forEach(function (p, i) {
                var li = document.createElement('li');
                li.className = 'rp-lb-item' + (i === 0 ? ' rp-lb-winner' : '') + (p.player_id === state.playerId ? ' rp-lb-you' : '');
                var medal = ['🥇', '🥈', '🥉'][i] || (i + 1) + '.';
                li.innerHTML =
                    '<span class="rp-lb-rank">' + medal + '</span>' +
                    '<span class="rp-lb-name">' + esc(p.name) + (p.player_id === state.playerId ? ' <em>(' + ROOM_T.you + ')</em>' : '') + '</span>' +
                    '<span class="rp-lb-score">' + p.score + ' / ' + (data.n_questions || state.questions.length) + '</span>' +
                    '<span class="rp-lb-pct">' + p.pct + '%</span>';
                lb.appendChild(li);
            });
        }

        // Subtitle: show finish status
        var subtitleEl = document.getElementById('rp-results-subtitle');
        var pendingCount = players.length - Object.keys(scores).length;
        if (subtitleEl) {
            subtitleEl.textContent = pendingCount > 0 ?
                ROOM_T.n_finished.replace('{n}', Object.keys(scores).length).replace('{total}', players.length) : '';
        }

        // Update waiting results section if some players haven't finished
        var pendingLb = document.getElementById('rp-partial-lb');
        if (pendingLb) {
            pendingLb.innerHTML = lb ? lb.innerHTML : '';
        }
        var wrCount = document.getElementById('rp-wr-count');
        if (wrCount) {
            wrCount.textContent = ROOM_T.n_finished
                .replace('{n}', Object.keys(scores).length)
                .replace('{total}', players.length);
        }
    }

    // ── Utilities ─────────────────────────────────────────────────────────────
    function showSection(id) {
        ['rp-lobby', 'rp-game', 'rp-results', 'rp-waiting-results'].forEach(function (s) {
            var el = document.getElementById(s);
            if (el) el.style.display = s === id ? '' : 'none';
        });
    }

    function showError(elId, msg) {
        var el = document.getElementById(elId);
        if (el) { el.textContent = msg; el.style.display = ''; }
    }
    function hideError(elId) {
        var el = document.getElementById(elId);
        if (el) { el.style.display = 'none'; }
    }

    function esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function formatVal(val, statInfo) {
        if (val === undefined || val === null || val === '') return '';
        var fmt = statInfo ? statInfo.format : null;
        var unit = statInfo ? (statInfo.unit || '') : '';
        if (fmt === 'integer') return Number(val).toLocaleString() + (unit ? ' ' + unit : '');
        if (fmt === 'decimal') return Number(val).toFixed(1) + (unit ? ' ' + unit : '');
        if (fmt === 'percent') return Number(val).toFixed(1) + '%';
        return Number(val).toLocaleString() + (unit ? ' ' + unit : '');
    }

    // ── Boot ──────────────────────────────────────────────────────────────────
    init();

}());
