"""Tournaments router — REST endpoints + WebSocket for multi-round PvP."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.auth import get_current_user, get_optional_user
from core.i18n import get_lang, t
from core.templates import templates


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    raise TypeError

def _clean_decimals(obj):
    """Convert DynamoDB Decimals to plain ints/floats for JSON serialization."""
    return json.loads(json.dumps(obj, default=_decimal_default))
from core.websocket_manager import tournament_manager as ws_mgr
from services.auth import decode_token
from services.games import GamesService
from services.matches import create_match, finish_match, save_match_player
from services.tournaments import (
    advance_round,
    all_round_players_finished,
    cancel_tournament,
    create_round,
    create_tournament,
    finish_round,
    finish_tournament,
    generate_round_questions,
    get_all_rounds,
    get_round,
    get_tournament,
    get_waiting_tournaments,
    join_tournament,
    mark_round_player_finished,
    pick_round_game_type,
    start_tournament,
    update_round_progress,
    update_scoreboard,
)
from services.analytics import track
from services.user_stats import record_match_result
from services.users import get_user_by_id
from services.scoring import process_ranked_attempt

router = APIRouter(tags=["tournaments"])

_games_service = GamesService()


# ── Pages ────────────────────────────────────────────────────────────────────

@router.get("/play/tournament")
async def tournament_lobby_page(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    lang = get_lang(request)
    return templates.TemplateResponse("tournaments/lobby.html", {
        "request": request, "user": user, "lang": lang,
    })


@router.get("/play/tournament/create")
async def tournament_create_page(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    lang = get_lang(request)
    games = _games_service.get_games()
    return templates.TemplateResponse("tournaments/create.html", {
        "request": request, "user": user, "lang": lang,
        "games": games,
    })


@router.get("/play/tournament/join")
async def tournament_join_page(request: Request, user: Optional[dict] = Depends(get_optional_user)):
    lang = get_lang(request)
    return templates.TemplateResponse("tournaments/join.html", {
        "request": request, "user": user, "lang": lang,
    })


@router.get("/tournaments/{tid}")
async def tournament_page(tid: str, request: Request, user: dict = Depends(get_current_user)):
    lang = get_lang(request)
    tourn = get_tournament(tid)
    if not tourn:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if user["user_id"] not in tourn.get("players", []):
        raise HTTPException(status_code=403, detail="Not a participant")

    rounds = get_all_rounds(tid)
    current_round_data = None
    cr = int(tourn.get("current_round", 0))
    if cr > 0:
        current_round_data = get_round(tid, cr)

    template = "tournaments/play.html"
    if tourn["status"] == "finished":
        template = "tournaments/results.html"

    # Clean Decimals from DynamoDB before passing to template
    tourn = _clean_decimals(tourn)

    # Build game name map from contents.json
    all_games = _games_service.get_games()
    game_name_map = {}
    for g in all_games:
        lang_key = "name_" + lang if lang != "es" else "name"
        game_name_map[g["id"]] = g.get(lang_key) or g.get("name_en") or g.get("name", g["id"])

    return templates.TemplateResponse(template, {
        "request": request, "user": user, "lang": lang,
        "tournament": tourn, "rounds": rounds,
        "current_round": current_round_data,
        "game_name_map": game_name_map,
    })


# ── REST API ─────────────────────────────────────────────────────────────────

class TournamentGameConfig(BaseModel):
    game_id: str
    num_questions: int = 10
    rounds: int = 1
    continent: str = "all"
    timed: bool = False


class CreateTournamentPayload(BaseModel):
    games: list[TournamentGameConfig]
    num_players: int = 2


VALID_GAME_IDS = {"ordering", "comparison", "geostats", "flags", "outline"}


@router.post("/api/tournaments/create")
async def api_create_tournament(payload: CreateTournamentPayload, user: dict = Depends(get_current_user)):
    if payload.num_players < 2 or payload.num_players > 10:
        raise HTTPException(status_code=400, detail="Players must be 2-10")
    if not payload.games:
        raise HTTPException(status_code=400, detail="At least one game required")

    # Count total rounds (each game.rounds contributes)
    total_rounds = sum(g.rounds for g in payload.games)
    if total_rounds > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 total rounds")

    for g in payload.games:
        if g.game_id not in VALID_GAME_IDS:
            raise HTTPException(status_code=400, detail=f"Invalid game type: {g.game_id}")
        if g.num_questions < 5 or g.num_questions > 50:
            raise HTTPException(status_code=400, detail="Questions must be 5-50")
        if g.rounds < 1 or g.rounds > 5:
            raise HTTPException(status_code=400, detail="Rounds per game must be 1-5")

    # Expand games into individual rounds
    rounds_config = []
    for g in payload.games:
        for _ in range(g.rounds):
            rounds_config.append({
                "game_id": g.game_id,
                "num_questions": g.num_questions,
                "continent": g.continent,
                "timed": g.timed,
            })

    config = {
        "rounds": rounds_config,
        "num_players": payload.num_players,
    }
    tourn = create_tournament(
        created_by=user["user_id"],
        username=user["username"],
        number_of_rounds=total_rounds,
        config=config,
    )
    track("tournament_created", {"tournament_id": tourn["tournament_id"], "user_id": user["user_id"]})
    return {"tournament_id": tourn["tournament_id"], "status": "waiting"}


@router.post("/api/tournaments/{tid}/join")
async def api_join_tournament(tid: str, user: dict = Depends(get_current_user)):
    tourn = get_tournament(tid)
    if not tourn:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tourn["status"] != "waiting":
        raise HTTPException(status_code=400, detail="Not waiting for players")
    if user["user_id"] in tourn.get("players", []):
        raise HTTPException(status_code=400, detail="Already joined")

    updated = join_tournament(tid, user["user_id"], user["username"])
    if not updated:
        raise HTTPException(status_code=400, detail="Could not join")

    await ws_mgr.broadcast_all(tid, {
        "type": "player_joined",
        "user_id": user["user_id"],
        "username": user["username"],
        "players": updated.get("players", []),
        "player_usernames": updated.get("player_usernames", {}),
    })
    track("tournament_joined", {"tournament_id": tid, "user_id": user["user_id"]})
    return {"tournament_id": tid, "status": "waiting"}


@router.post("/api/tournaments/{tid}/start")
async def api_start_tournament(tid: str, user: dict = Depends(get_current_user)):
    tourn = get_tournament(tid)
    if not tourn:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tourn["created_by"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only creator can start")
    if tourn["status"] != "waiting":
        raise HTTPException(status_code=400, detail="Already started")
    if len(tourn.get("players", [])) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 players")

    start_tournament(tid)
    rnd = _create_next_round(tid, 1, tourn)

    config = tourn.get("config", {})
    rounds_config = config.get("rounds", [])

    await ws_mgr.broadcast_all(tid, {
        "type": "tournament_started",
        "round_number": 1,
        "game_type": rnd["game_type"],
        "total_rounds": int(tourn.get("number_of_rounds", 1)),
        "rounds_config": rounds_config,
    })
    return {"started": True, "round": 1}


@router.post("/api/tournaments/{tid}/cancel")
async def api_cancel_tournament(tid: str, user: dict = Depends(get_current_user)):
    tourn = get_tournament(tid)
    if not tourn:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tourn["created_by"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only creator can cancel")
    cancel_tournament(tid)
    await ws_mgr.broadcast_all(tid, {"type": "tournament_cancelled"})
    return {"cancelled": True}


@router.get("/api/tournaments/waiting")
async def api_waiting_tournaments(user: dict = Depends(get_current_user)):
    tournaments = get_waiting_tournaments()
    return [
        {
            "tournament_id": t["tournament_id"],
            "config": t.get("config", {}),
            "created_by": t["created_by"],
            "creator_username": t.get("player_usernames", {}).get(t["created_by"], "?"),
            "number_of_rounds": int(t.get("number_of_rounds", 5)),
            "player_count": len(t.get("players", [])),
            "created_at": t["created_at"],
        }
        for t in tournaments
        if t["created_by"] != user["user_id"]
    ]


@router.get("/api/tournaments/{tid}")
async def api_get_tournament(tid: str, user: dict = Depends(get_current_user)):
    tourn = get_tournament(tid)
    if not tourn:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return _safe_tournament(tourn)


@router.get("/api/tournaments/{tid}/round/{round_num}/questions")
async def api_round_questions(tid: str, round_num: int, user: dict = Depends(get_current_user)):
    tourn = get_tournament(tid)
    if not tourn:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if user["user_id"] not in tourn.get("players", []):
        raise HTTPException(status_code=403, detail="Not a participant")

    rnd = get_round(tid, round_num)
    if not rnd:
        raise HTTPException(status_code=404, detail="Round not found")
    if rnd["status"] != "active":
        raise HTTPException(status_code=400, detail="Round not active")

    questions = rnd.get("questions", [])
    game_type = rnd.get("game_type", "ordering")

    safe_q = _strip_answers(questions, game_type)
    return {"questions": safe_q, "game_type": game_type, "round_number": round_num}


class TournamentAnswerPayload(BaseModel):
    round_number: int
    question_index: int
    answer: str | list[str]


@router.post("/api/tournaments/{tid}/answer")
async def api_tournament_answer(tid: str, payload: TournamentAnswerPayload, user: dict = Depends(get_current_user)):
    tourn = get_tournament(tid)
    if not tourn:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tourn["status"] != "active":
        raise HTTPException(status_code=400, detail="Tournament not active")
    if user["user_id"] not in tourn.get("players", []):
        raise HTTPException(status_code=403, detail="Not a participant")

    rnd = get_round(tid, payload.round_number)
    if not rnd or rnd["status"] != "active":
        raise HTTPException(status_code=400, detail="Round not active")

    questions = rnd.get("questions", [])
    qi = payload.question_index
    if qi < 0 or qi >= len(questions):
        raise HTTPException(status_code=400, detail="Invalid question index")

    q = questions[qi]
    game_type = rnd.get("game_type", "ordering")
    correct = False

    if game_type == "ordering":
        correct = payload.answer == q.get("correct_order", [])
    elif game_type == "comparison":
        correct = payload.answer == q.get("correct_iso", "")
    elif game_type in ("flags", "outline"):
        correct = payload.answer == q.get("correct_iso", "")
    elif game_type == "geostats":
        correct = payload.answer == q.get("correct_iso", "")

    current_score = int(rnd.get("round_scores", {}).get(user["user_id"], 0))
    if correct:
        current_score += 1

    update_round_progress(tid, payload.round_number, user["user_id"], qi + 1, current_score)

    feedback = {"correct": correct, "question_index": qi}
    feedback.update(_build_feedback(q, game_type))

    # Broadcast opponent progress
    await ws_mgr.broadcast(tid, {
        "type": "opponent_progress",
        "user_id": user["user_id"],
        "round_number": payload.round_number,
        "question_index": qi + 1,
        "score": current_score,
    }, exclude=user["user_id"])

    is_last = (qi + 1) >= len(questions)
    if is_last:
        mark_round_player_finished(tid, payload.round_number, user["user_id"], current_score)
        update_scoreboard(tid, user["user_id"], current_score)

        rnd_updated = get_round(tid, payload.round_number)
        players = tourn.get("players", [])

        if rnd_updated and all_round_players_finished(rnd_updated, players):
            finish_round(tid, payload.round_number)
            tourn_updated = get_tournament(tid)
            total_rounds = int(tourn.get("number_of_rounds", 5))
            next_round = payload.round_number + 1

            if next_round > total_rounds:
                # Tournament finished
                finish_tournament(tid)
                await _persist_tournament_results(tourn_updated)
                track("tournament_finished", {"tournament_id": tid, "scoreboard": _int_map(tourn_updated.get("scoreboard", {}))})
                await ws_mgr.broadcast_all(tid, {
                    "type": "tournament_finished",
                    "scoreboard": _int_map(tourn_updated.get("scoreboard", {})),
                    "player_usernames": tourn_updated.get("player_usernames", {}),
                })
            else:
                # Start next round
                advance_round(tid, next_round)
                track("tournament_round_finished", {"tournament_id": tid, "round": payload.round_number})
                new_rnd = _create_next_round(tid, next_round, tourn_updated)
                await ws_mgr.broadcast_all(tid, {
                    "type": "round_finished",
                    "round_number": payload.round_number,
                    "round_scores": _int_map(rnd_updated.get("round_scores", {})),
                    "scoreboard": _int_map(tourn_updated.get("scoreboard", {})),
                    "next_round": next_round,
                    "next_game_type": new_rnd["game_type"],
                })
        else:
            await ws_mgr.broadcast(tid, {
                "type": "player_round_finished",
                "user_id": user["user_id"],
                "round_number": payload.round_number,
                "score": current_score,
            }, exclude=user["user_id"])

    feedback["is_last"] = is_last
    feedback["current_score"] = current_score
    feedback["total_answered"] = qi + 1
    return feedback


# ── WebSocket ────────────────────────────────────────────────────────────────

@router.websocket("/ws/tournament/{tid}")
async def tournament_websocket(websocket: WebSocket, tid: str):
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001)
        return
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001)
        return
    user = get_user_by_id(payload["sub"])
    if not user:
        await websocket.close(code=4001)
        return

    uid = user["user_id"]
    tourn = get_tournament(tid)
    if not tourn or uid not in tourn.get("players", []):
        await websocket.close(code=4003)
        return

    await ws_mgr.connect(tid, uid, websocket)
    await ws_mgr.broadcast(tid, {
        "type": "user_connected",
        "user_id": uid,
        "username": user.get("username", ""),
        "connected_users": ws_mgr.get_connected_users(tid),
    }, exclude=uid)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_mgr.disconnect(tid, uid)
        await ws_mgr.broadcast(tid, {
            "type": "user_disconnected",
            "user_id": uid,
            "connected_users": ws_mgr.get_connected_users(tid),
        })


# ── Helpers ──────────────────────────────────────────────────────────────────

def _int_map(m: dict) -> dict:
    return {k: int(v) for k, v in m.items()}


def _safe_tournament(tourn: dict) -> dict:
    return {
        "tournament_id": tourn["tournament_id"],
        "status": tourn["status"],
        "number_of_rounds": int(tourn.get("number_of_rounds", 5)),
        "current_round": int(tourn.get("current_round", 0)),
        "config": tourn.get("config", {}),
        "players": tourn.get("players", []),
        "player_usernames": tourn.get("player_usernames", {}),
        "scoreboard": _int_map(tourn.get("scoreboard", {})),
        "created_by": tourn["created_by"],
    }


def _create_next_round(tid: str, round_number: int, tourn: dict) -> dict:
    config = tourn.get("config", {})
    rounds_config = config.get("rounds", [])
    idx = round_number - 1  # 0-based
    if idx < len(rounds_config):
        rc = rounds_config[idx]
        game_type = rc.get("game_id", "ordering")
        round_config = {
            "num_questions": rc.get("num_questions", 10),
            "continent": rc.get("continent", "all"),
            "timed": rc.get("timed", False),
        }
    else:
        # Fallback for old-format tournaments
        game_type = pick_round_game_type(config)
        round_config = config

    questions = generate_round_questions(game_type, round_config)
    players = tourn.get("players", [])
    return create_round(tid, round_number, game_type, round_config, questions, players)


def _strip_answers(questions: list[dict], game_type: str) -> list[dict]:
    """Remove answer fields from questions before sending to client."""
    safe = []
    for q in questions:
        if game_type == "ordering":
            safe.append({
                "stat": q.get("stat"), "stat_info": q.get("stat_info"),
                "ascending": q.get("ascending"), "countries": q.get("countries"),
            })
        elif game_type == "comparison":
            safe.append({
                "stat": q.get("stat"), "stat_info": q.get("stat_info"),
                "countries": q.get("countries"),
            })
        elif game_type in ("flags", "outline"):
            safe.append({
                "options": q.get("options", []),
                "display": q.get("display", {}),
            })
        elif game_type == "geostats":
            safe.append({
                "chart_data": q.get("chart_data", {}),
                "stat_info": q.get("stat_info"),
                "options": q.get("options", []),
            })
        else:
            safe.append(q)
    return safe


def _build_feedback(q: dict, game_type: str) -> dict:
    """Build feedback dict with correct answers for the client."""
    if game_type == "ordering":
        return {
            "correct_order": q.get("correct_order", []),
            "correct_values": q.get("correct_values", {}),
        }
    elif game_type == "comparison":
        return {
            "correct_iso": q.get("correct_iso", ""),
            "values": q.get("values", {}),
        }
    elif game_type in ("flags", "outline"):
        return {"correct_iso": q.get("correct_iso", "")}
    elif game_type == "geostats":
        return {"correct_iso": q.get("correct_iso", "")}
    return {}


async def _persist_tournament_results(tourn: dict) -> None:
    """Create match records per round and update user_stats."""
    players = tourn.get("players", [])
    scoreboard = tourn.get("scoreboard", {})
    config = tourn.get("config", {})
    tid = tourn["tournament_id"]

    sorted_players = sorted(players, key=lambda p: int(scoreboard.get(p, 0)), reverse=True)
    winner_id = sorted_players[0] if sorted_players else ""

    # One aggregate match for the tournament
    match = create_match(
        mode="tournament_round",
        game_type="tournament",
        config=config,
        total_players=len(players),
    )
    finish_match(match_id=match["match_id"], winner_id=winner_id)

    total_rounds = int(tourn.get("number_of_rounds", 1))
    rounds_config = config.get("rounds", [])
    total_questions = sum(rc.get("num_questions", 10) for rc in rounds_config) if rounds_config else total_rounds * 10
    for rank, pid in enumerate(sorted_players, 1):
        total_score = int(scoreboard.get(pid, 0))
        accuracy = (total_score / total_questions * 100) if total_questions > 0 else 0
        save_match_player(
            match_id=match["match_id"],
            user_id=pid,
            score=total_score,
            rank=rank,
            accuracy=accuracy,
        )
        record_match_result(
            user_id=pid,
            game_type="tournament",
            score=total_score,
            total=total_questions,
            accuracy=accuracy,
            time_ms=0,
            won=(pid == winner_id),
        )

    # Feed scoring engine per-round for rankings
    try:
        all_rounds = get_all_rounds(tid)
        usernames = {}
        for pid in players:
            uinfo = get_user_by_id(pid)
            usernames[pid] = uinfo.get("username", "") if uinfo else ""
        for rnd in all_rounds:
            rnd_gt = rnd.get("game_type", "ordering")
            rnd_config = rnd.get("config", {})
            rnd_scores = rnd.get("round_scores", {})
            rnd_questions = rnd.get("questions", [])
            rnd_total = len(rnd_questions)
            if rnd_total == 0:
                continue
            for pid in players:
                rs = int(rnd_scores.get(pid, 0))
                process_ranked_attempt(
                    user_id=pid,
                    game_type=rnd_gt,
                    score=rs,
                    total=rnd_total,
                    num_questions=rnd_total,
                    time_ms=0,
                    config=rnd_config,
                    username=usernames.get(pid, ""),
                )
    except Exception:
        pass  # Don't break tournament flow
