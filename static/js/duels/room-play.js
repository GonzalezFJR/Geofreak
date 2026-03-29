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
        finished: false,     // true once player has submitted their score
        geoGuessPos: null,   // 0-1 fraction for geostats
    };

    // ── Ordering drag/touch state (module-level, not per-question) ────────────
    var ordDragSrc = null;
    var ordTouchItem = null;

    // ── Outline map state ─────────────────────────────────────────────────────
    var _outlineMap = null;

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
        } else if (data.status === 'playing' && state.finished) {
            // Player finished — keep updating the live waiting table
            updateWaitingView(data);
        } else if (data.status === 'playing') {
            // Still in game — do nothing (game loop handles itself)
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
            var isQuiz = (ROOM_GAME_ID === 'flags' || ROOM_GAME_ID === 'outline');
            var diffKey = 'diff_' + (cfg.difficulty || 'normal');
            var diffLabel = ROOM_T[diffKey] || cfg.difficulty || 'normal';
            cfgEl.innerHTML =
                '<span>' + ROOM_T.cfg_items + ': <b>' + (cfg.n_items || '?') + '</b></span>' +
                (isQuiz ? '' : '<span>' + ROOM_T.cfg_difficulty + ': <b>' + diffLabel + '</b></span>');
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
        confirmOrder: function () {
            var q = state.questions[state.qIndex];
            if (!q) return;
            document.getElementById('rp-ord-confirm').style.display = 'none';

            var items = document.querySelectorAll('#rp-ord-list .ordering-item');
            var submitted = Array.from(items).map(function (el) { return el.getAttribute('data-iso'); });
            var correct = q.correct_order || [];
            var isCorrect = JSON.stringify(submitted) === JSON.stringify(correct);
            if (isCorrect) state.score++;
            updateHud();

            // Show inline values + correct/wrong per item — same as solo ordering-game.js
            var lang = CURRENT_LANG;
            items.forEach(function (el, i) {
                var iso = el.getAttribute('data-iso');
                var correctIdx = correct.indexOf(iso);
                var val = q.correct_values ? q.correct_values[iso] : '';
                var formatted = val !== undefined && val !== '' ? formatVal(val, q.stat_info) : '';

                if (formatted) {
                    var badge = document.createElement('span');
                    badge.className = 'ordering-value';
                    badge.textContent = formatted;
                    el.appendChild(badge);
                }

                var rank = el.querySelector('.ordering-rank');
                if (rank) {
                    rank.textContent = correctIdx + 1;
                    rank.classList.add(iso === correct[i] ? 'rank-correct' : 'rank-wrong');
                }
                el.classList.add(iso === correct[i] ? 'correct' : 'wrong');
                el.setAttribute('draggable', 'false');
                el.style.cursor = 'default';
            });

            var fbEl = document.getElementById('rp-ord-fb');
            if (fbEl) {
                fbEl.className = 'ordering-feedback ' + (isCorrect ? 'correct' : 'wrong');
                fbEl.textContent = isCorrect ? ROOM_T.correct : ROOM_T.wrong;
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
                var countries = q.countries_lookup || {};
                var cData = countries[target] || {};
                var cName = cData['name_' + lang] || cData.name || target;
                var cFlag = cData.flag_emoji || '';
                var cVal = q.curve ? q.curve[targetIdx] : '';
                var cls = isCorrect ? 'correct' : (dist <= 0.3 ? 'warning' : 'wrong');
                var msg = isCorrect ? ROOM_T.geo_correct : (dist <= 0.3 ? ROOM_T.geo_close : ROOM_T.geo_wrong);
                fbEl.className = 'geostats-feedback ' + cls;
                fbEl.textContent = msg + '  —  ' + cFlag + ' ' + cName + ' (' + formatVal(cVal, q.stat_info) + ')';
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

        // ── Quiz answer handlers ─────────────────────────────────────────────
        quizCheck: function () {
            var input = document.getElementById('rp-quiz-input');
            if (!input) return;
            var answer = input.value.trim();
            if (!answer) return;

            var q = state.questions[state.qIndex];
            var acceptable = GeoUtils.getCountryNames(q);
            var normalized = GeoUtils.normalize(answer);
            var fb = document.getElementById('rp-quiz-fb');

            if (acceptable.has(normalized)) {
                state.score++;
                updateHud();
                input.className = 'correct';
                if (fb) {
                    fb.className = 'quiz-feedback correct';
                    fb.textContent = (ROOM_T.quiz_correct || '✅ {name}').replace('{name}', getLocalName(q));
                }
                setTimeout(function () { RoomPlay.nextQuestion(); }, 800);
            } else {
                input.className = 'wrong';
                if (fb) {
                    fb.className = 'quiz-feedback wrong';
                    fb.textContent = ROOM_T.quiz_wrong || '❌ Wrong, try again';
                }
                setTimeout(function () { if (input) input.className = ''; }, 400);
                input.select();
            }
        },

        quizSkip: function () {
            var q = state.questions[state.qIndex];
            var fb = document.getElementById('rp-quiz-fb');
            var name = getLocalName(q);
            if (fb) {
                fb.className = 'quiz-feedback wrong';
                fb.textContent = (ROOM_T.quiz_skipped || '⏭️ {name}').replace('{name}', name);
            }
            var input = document.getElementById('rp-quiz-input');
            if (input) { input.value = name; input.className = 'wrong'; }
            setTimeout(function () { RoomPlay.nextQuestion(); }, 1200);
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
        ['rp-cmp', 'rp-ord', 'rp-geo', 'rp-quiz'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });

        if (gameType === 'comparison') {
            renderComparison(q);
        } else if (gameType === 'ordering') {
            renderOrdering(q);
        } else if (gameType === 'geostats') {
            renderGeostats(q);
        } else if (gameType === 'flags' || gameType === 'outline') {
            renderQuiz(q, gameType);
        }
    }

    // ── Comparison — same CSS classes & shuffle as solo comparison-game.js ─────
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
            // Randomise order — same as solo (Math.random < 0.5 → reverse)
            var displayCountries = q.countries.slice();
            if (Math.random() < 0.5) displayCountries.reverse();

            displayCountries.forEach(function (c) {
                var div = document.createElement('div');
                div.className = 'comparison-card';
                div.setAttribute('data-iso', c.iso_a3);
                var cName = c['name_' + lang] || c.name;
                var subtitle = c.country_name ? '<div class="comparison-country">' + esc(c.flag_emoji || '') + ' ' + esc(c.country_name) + '</div>' : '';
                div.innerHTML =
                    '<div class="comparison-flag">' + (c.country_name ? '' : (c.flag_emoji || '')) + '</div>' +
                    '<div class="comparison-name">' + esc(cName) + '</div>' +
                    subtitle +
                    '<div class="comparison-value" id="rp-val-' + c.iso_a3 + '" style="display:none"></div>';
                div.addEventListener('click', function () { handleCmpClick(q, c.iso_a3); });
                cardsEl.appendChild(div);
            });
        }
        var fbEl = document.getElementById('rp-cmp-fb');
        if (fbEl) { fbEl.className = 'comparison-feedback'; fbEl.textContent = ''; }
    }

    function handleCmpClick(q, chosenIso) {
        // Disable all cards
        document.querySelectorAll('#rp-cmp-cards .comparison-card').forEach(function (div) {
            div.style.pointerEvents = 'none';
        });

        var isCorrect = (chosenIso === q.correct_iso);
        if (isCorrect) state.score++;
        updateHud();

        // Reveal values and mark correct/wrong — same pattern as solo
        document.querySelectorAll('#rp-cmp-cards .comparison-card').forEach(function (div) {
            var iso = div.getAttribute('data-iso');
            var val = q.values ? q.values[iso] : undefined;
            var valFmt = val !== undefined ? formatVal(val, q.stat_info) : '';
            var valEl = document.getElementById('rp-val-' + iso);
            if (valEl && valFmt) { valEl.textContent = valFmt; valEl.style.display = ''; }
            if (iso === q.correct_iso) div.classList.add('correct');
            else if (iso === chosenIso) div.classList.add('wrong');
        });

        var fbEl = document.getElementById('rp-cmp-fb');
        if (fbEl) {
            fbEl.className = 'comparison-feedback ' + (isCorrect ? 'correct' : 'wrong');
            fbEl.textContent = isCorrect ? ROOM_T.correct : ROOM_T.wrong;
        }

        setTimeout(function () { RoomPlay.nextQuestion(); }, 1800);
    }

    // ── Ordering — same CSS classes, drag/drop & touch as solo ordering-game.js ─
    function renderOrdering(q) {
        var panel = document.getElementById('rp-ord');
        if (!panel) return;
        panel.style.display = '';

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
                var el = document.createElement('div');
                el.className = 'ordering-item';
                el.setAttribute('draggable', 'true');
                el.setAttribute('data-iso', c.iso_a3);
                var cName = c['name_' + lang] || c.name;
                var flagSpan = c.country_name
                    ? '<span class="ordering-flag">' + (c.flag_emoji || '') + '</span>'
                    : '<span class="ordering-flag">' + (c.flag_emoji || '') + '</span>';
                var countrySpan = c.country_name
                    ? '<span class="ordering-country">' + esc(c.country_name) + '</span>'
                    : '';
                el.innerHTML =
                    '<span class="ordering-rank">' + (i + 1) + '</span>' +
                    '<span class="ordering-handle">☰</span>' +
                    flagSpan +
                    '<span class="ordering-name">' + esc(cName) + '</span>' +
                    countrySpan;
                el.addEventListener('dragstart', ordDragStart);
                el.addEventListener('dragover', ordDragOver);
                el.addEventListener('drop', ordDrop);
                el.addEventListener('dragend', ordDragEnd);
                el.addEventListener('touchstart', ordTouchStart, { passive: false });
                el.addEventListener('touchmove', ordTouchMove, { passive: false });
                el.addEventListener('touchend', ordTouchEnd);
                list.appendChild(el);
            });
        }

        var confirmBtn = document.getElementById('rp-ord-confirm');
        if (confirmBtn) { confirmBtn.style.display = ''; confirmBtn.disabled = false; }
        var fbEl = document.getElementById('rp-ord-fb');
        if (fbEl) { fbEl.className = 'ordering-feedback'; fbEl.textContent = ''; }
        var nextBtn = document.getElementById('rp-ord-next');
        if (nextBtn) nextBtn.style.display = 'none';
    }

    // Drag handlers (same logic as ordering-game.js)
    function ordDragStart(e) {
        ordDragSrc = this;
        this.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', '');
    }
    function ordDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        var target = ordClosestItem(e.target);
        if (target && target !== ordDragSrc) {
            var list = document.getElementById('rp-ord-list');
            var items = Array.from(list.children);
            if (items.indexOf(ordDragSrc) < items.indexOf(target)) {
                list.insertBefore(ordDragSrc, target.nextSibling);
            } else {
                list.insertBefore(ordDragSrc, target);
            }
        }
    }
    function ordDrop(e) { e.preventDefault(); }
    function ordDragEnd() {
        this.classList.remove('dragging');
        ordDragSrc = null;
        ordUpdateRanks();
    }
    function ordClosestItem(el) {
        while (el && !el.classList.contains('ordering-item')) el = el.parentElement;
        return el;
    }
    function ordUpdateRanks() {
        document.querySelectorAll('#rp-ord-list .ordering-item').forEach(function (el, i) {
            var rank = el.querySelector('.ordering-rank');
            if (rank) rank.textContent = i + 1;
        });
    }
    // Touch handlers (same logic as ordering-game.js)
    function ordTouchStart(e) {
        ordTouchItem = this;
        this.classList.add('dragging');
        e.preventDefault();
    }
    function ordTouchMove(e) {
        if (!ordTouchItem) return;
        e.preventDefault();
        var touch = e.touches[0];
        var target = document.elementFromPoint(touch.clientX, touch.clientY);
        var item = ordClosestItem(target);
        if (item && item !== ordTouchItem) {
            var list = document.getElementById('rp-ord-list');
            var items = Array.from(list.children);
            if (items.indexOf(ordTouchItem) < items.indexOf(item)) {
                list.insertBefore(ordTouchItem, item.nextSibling);
            } else {
                list.insertBefore(ordTouchItem, item);
            }
        }
    }
    function ordTouchEnd() {
        if (ordTouchItem) {
            ordTouchItem.classList.remove('dragging');
            ordTouchItem = null;
            ordUpdateRanks();
        }
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
        var cCountry = cData.country_name || '';

        var promptEl = document.getElementById('rp-geo-prompt');
        if (promptEl) promptEl.innerHTML = ROOM_T.geo_prompt.replace('{stat}', '<em>' + esc(statLabel) + '</em>');

        var targetEl = document.getElementById('rp-geo-target');
        var countryHtml = cCountry ? ' <span class="rp-geo-country">(' + esc(cFlag) + ' ' + esc(cCountry) + ')</span>' : '';
        if (targetEl) targetEl.innerHTML = '<span class="rp-geo-flag">' + (cCountry ? '' : cFlag) + '</span> <span class="rp-geo-cname">' + esc(cName) + '</span>' + countryHtml;

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
        if (fbEl) { fbEl.className = 'geostats-feedback'; fbEl.textContent = ''; }
        var nextBtn = document.getElementById('rp-geo-next');
        if (nextBtn) nextBtn.style.display = 'none';
    }

    // ── Quiz (flags / outline) ────────────────────────────────────────────────
    function getLocalName(q) {
        var lang = CURRENT_LANG;
        return q['name_' + lang] || q.name_en || q.name || q.iso_a3;
    }

    function renderQuiz(q, gameType) {
        var panel = document.getElementById('rp-quiz');
        if (!panel) return;
        panel.style.display = '';

        var promptEl = document.getElementById('rp-quiz-prompt');
        if (promptEl) {
            promptEl.textContent = gameType === 'flags'
                ? ROOM_T.quiz_prompt_flag
                : ROOM_T.quiz_prompt_outline;
        }

        var display = document.getElementById('rp-quiz-display');
        if (display) {
            display.innerHTML = '';
            if (gameType === 'flags') {
                var img = document.createElement('img');
                img.className = 'quiz-flag';
                img.src = '/static/data/images/flags/' + q.iso_a3 + '.svg';
                img.onerror = function () { display.innerHTML = '<div style="padding:40px;color:#94a3b8;">🏳️</div>'; };
                display.appendChild(img);
            } else {
                // outline — render Leaflet map
                display.innerHTML = '<div class="outline-map-wrapper" id="rp-outline-map"></div>';
                if (_outlineMap) { _outlineMap.remove(); _outlineMap = null; }
                fetch('/api/geojson/' + q.iso_a3)
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .then(function (geojson) {
                        if (!geojson) { display.innerHTML = '<div style="padding:40px;color:#94a3b8;">🗺️</div>'; return; }
                        _outlineMap = L.map('rp-outline-map', {
                            zoomControl: false, attributionControl: false,
                            dragging: false, scrollWheelZoom: false,
                            doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false,
                        });
                        var layer = L.geoJSON(geojson, {
                            style: { fillColor: '#1e293b', fillOpacity: 0.8, color: '#0f172a', weight: 2 }
                        }).addTo(_outlineMap);
                        _outlineMap.fitBounds(layer.getBounds(), { padding: [20, 20] });
                    })
                    .catch(function () { display.innerHTML = '<div style="padding:40px;color:#94a3b8;">🗺️</div>'; });
            }
        }

        var input = document.getElementById('rp-quiz-input');
        if (input) {
            input.value = '';
            input.className = '';
            input.onkeydown = function (e) { if (e.key === 'Enter') RoomPlay.quizCheck(); };
            input.focus();
        }

        var fb = document.getElementById('rp-quiz-fb');
        if (fb) { fb.className = 'quiz-feedback'; fb.textContent = ''; }
    }

    // ── Finish game ───────────────────────────────────────────────────────────
    function finishGame() {
        if (state.timerInterval) { clearInterval(state.timerInterval); state.timerInterval = null; }
        var timeMs = Date.now() - state.startTime;
        var total  = state.questions.length;
        state.finished = true;

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
        startPolling(3000);
    }

    // ── Live waiting table ────────────────────────────────────────────────────
    function updateWaitingView(data) {
        var players = data.players || [];
        var scores  = data.scores  || {};
        var total   = data.n_questions || state.questions.length;

        // Update subtitle count
        var finishedCount = Object.keys(scores).length;
        var wrCount = document.getElementById('rp-wr-count');
        if (wrCount) {
            wrCount.textContent = ROOM_T.n_finished
                .replace('{n}', finishedCount)
                .replace('{total}', players.length);
        }

        // Split into finished / still playing
        var finished = [], playing = [];
        players.forEach(function (p) {
            var s = scores[p.player_id];
            if (s) {
                finished.push({ name: p.name, player_id: p.player_id, is_guest: p.is_guest,
                    score: s.score || 0, pct: s.pct || 0, time_ms: s.time_ms || 0 });
            } else {
                playing.push(p);
            }
        });
        finished.sort(function (a, b) { return b.score - a.score || a.time_ms - b.time_ms; });

        var tbody = document.getElementById('rp-wr-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        var rank = 1;
        finished.forEach(function (p) {
            var isYou = (p.player_id === state.playerId);
            var medals = ['🥇', '🥈', '🥉'];
            var rankCell = rank <= 3 ? medals[rank - 1] : rank + '.';
            var tr = document.createElement('tr');
            tr.className = 'rp-wr-row rp-wr-finished' + (isYou ? ' rp-wr-you' : '');
            tr.innerHTML =
                '<td class="rp-wr-rank">' + rankCell + '</td>' +
                '<td class="rp-wr-name">' + esc(p.name) +
                    (isYou ? ' <span class="rp-badge-you">' + ROOM_T.you + '</span>' : '') + '</td>' +
                '<td class="rp-wr-score">' + p.score + ' / ' + total + '</td>' +
                '<td class="rp-wr-time">' + formatTime(p.time_ms) + '</td>' +
                '<td class="rp-wr-status rp-wr-done">✅</td>';
            tbody.appendChild(tr);
            rank++;
        });

        playing.forEach(function (p) {
            var isYou = (p.player_id === state.playerId);
            var tr = document.createElement('tr');
            tr.className = 'rp-wr-row rp-wr-playing' + (isYou ? ' rp-wr-you' : '');
            tr.innerHTML =
                '<td class="rp-wr-rank">—</td>' +
                '<td class="rp-wr-name">' + esc(p.name) + '</td>' +
                '<td class="rp-wr-score">—</td>' +
                '<td class="rp-wr-time">—</td>' +
                '<td class="rp-wr-status rp-wr-still-playing">' + esc(ROOM_T.still_playing) + '</td>';
            tbody.appendChild(tr);
        });
    }

    function formatTime(ms) {
        var secs = Math.floor((ms || 0) / 1000);
        var m = Math.floor(secs / 60), s = secs % 60;
        return m + ':' + (s < 10 ? '0' : '') + s;
    }

    // ── Results ────────────────────────────────────────────────────────────────
    function showResults(data) {
        updateWaitingView(data); // sync the waiting table one last time
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
