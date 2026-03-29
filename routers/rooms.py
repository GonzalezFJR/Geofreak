"""Rooms router — multiplayer duel rooms with up to 10 players.

URL structure:
  GET  /duel/{game_id}               → room lobby (create / join)
  GET  /duel/{game_id}/room/{code}   → room page (waiting + game + results)

API:
  POST /api/rooms/create
  POST /api/rooms/{code}/join
  POST /api/rooms/{code}/start
  GET  /api/rooms/{code}/state
  GET  /api/rooms/{code}/questions
  POST /api/rooms/{code}/score
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.auth import get_optional_user
from core.i18n import get_lang
from core.templates import templates
from services.games import GamesService
from services.quiz import generate_comparison_set, generate_ordering_set, generate_geostats_set, generate_quiz_set
from services.rooms import MAX_PLAYERS, create_room, get_room, join_room, start_room, submit_score

router = APIRouter(tags=["rooms"])
_games_svc = GamesService()

_ALLOWED_GAMES = {"ordering", "comparison", "geostats", "flags", "outline"}
_QUIZ_GAMES = {"flags", "outline"}


# ── Pages ─────────────────────────────────────────────────────────────────────

@router.get("/duel/{game_id}", response_class=HTMLResponse)
async def room_lobby_page(
    request: Request,
    game_id: str,
    user: Optional[dict] = Depends(get_optional_user),
):
    if game_id not in _ALLOWED_GAMES:
        raise HTTPException(status_code=404)
    lang = get_lang(request)
    game = _games_svc.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("duels/room_lobby.html", {
        "request": request, "user": user, "lang": lang,
        "game": game, "game_json": json.dumps(game, ensure_ascii=False),
    })


@router.get("/duel/{game_id}/room/{code}", response_class=HTMLResponse)
async def room_play_page(
    request: Request,
    game_id: str,
    code: str,
    user: Optional[dict] = Depends(get_optional_user),
):
    lang = get_lang(request)
    game = _games_svc.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("duels/room_play.html", {
        "request": request, "user": user, "lang": lang,
        "game": game, "game_json": json.dumps(game, ensure_ascii=False),
        "room_code": code.upper(),
    })


# ── REST API ──────────────────────────────────────────────────────────────────

class CreateRoomPayload(BaseModel):
    game_id: str
    n_items: int = 10
    difficulty: str = "normal"
    countdown: bool = True
    dataset: str = "countries"
    continent: str = "all"
    country_filter: str = ""
    guest_id: Optional[str] = None
    guest_name: Optional[str] = None


@router.post("/api/rooms/create")
async def api_create_room(
    payload: CreateRoomPayload,
    user: Optional[dict] = Depends(get_optional_user),
):
    _ALLOWED_DATASETS = {"countries", "cities", "us-states", "spain-provinces", "russia-regions", "france-regions", "italy-regions", "germany-states"}
    if payload.game_id not in _ALLOWED_GAMES:
        raise HTTPException(status_code=400, detail="invalid_game")
    if not 3 <= payload.n_items <= 50:
        raise HTTPException(status_code=400, detail="n_items must be 3-50")
    if payload.game_id not in _QUIZ_GAMES and payload.difficulty not in ("easy", "normal", "hard", "very_hard", "extreme"):
        raise HTTPException(status_code=400, detail="invalid_difficulty")
    if payload.dataset not in _ALLOWED_DATASETS:
        raise HTTPException(status_code=400, detail="invalid_dataset")

    if user:
        player_id = user["user_id"]
        player_name = user["username"]
        is_guest = False
        uid = user["user_id"]
    else:
        if not payload.guest_id or not payload.guest_name or not payload.guest_name.strip():
            raise HTTPException(status_code=400, detail="guest_id and guest_name required")
        player_id = payload.guest_id[:64]
        player_name = payload.guest_name.strip()[:30]
        is_guest = True
        uid = None

    config = {
        "n_items": payload.n_items,
        "difficulty": payload.difficulty,
        "countdown": payload.countdown,
        "dataset": payload.dataset,
        "continent": payload.continent,
        "country_filter": payload.country_filter,
    }
    room = create_room(
        game_id=payload.game_id,
        host_player_id=player_id,
        host_name=player_name,
        is_host_guest=is_guest,
        host_user_id=uid,
        config=config,
    )
    return {"code": room["room_code"], "player_id": player_id}


class JoinRoomPayload(BaseModel):
    guest_id: Optional[str] = None
    guest_name: Optional[str] = None


@router.post("/api/rooms/{code}/join")
async def api_join_room(
    code: str,
    payload: JoinRoomPayload,
    user: Optional[dict] = Depends(get_optional_user),
):
    if user:
        player_id = user["user_id"]
        player_name = user["username"]
        is_guest = False
        uid = user["user_id"]
    else:
        if not payload.guest_id or not payload.guest_name or not payload.guest_name.strip():
            raise HTTPException(status_code=400, detail="guest_id and guest_name required")
        player_id = payload.guest_id[:64]
        player_name = payload.guest_name.strip()[:30]
        is_guest = True
        uid = None

    room, error = join_room(code, player_id, player_name, is_guest, uid)
    _ERRORS = {
        "not_found": (404, "room_not_found"),
        "already_started": (400, "already_started"),
        "full": (400, "room_full"),
        "expired": (400, "room_expired"),
    }
    if error and error in _ERRORS:
        status_code, detail = _ERRORS[error]
        raise HTTPException(status_code=status_code, detail=detail)

    return {"code": code.upper(), "player_id": player_id, "game_id": room["game_id"]}


class StartRoomPayload(BaseModel):
    player_id: str  # host's player_id (needed for guest hosts)


@router.post("/api/rooms/{code}/start")
async def api_start_room(
    code: str,
    payload: StartRoomPayload,
    user: Optional[dict] = Depends(get_optional_user),
):
    # Determine host identity
    host_player_id = user["user_id"] if user else payload.player_id

    room = get_room(code)
    if not room:
        raise HTTPException(status_code=404, detail="room_not_found")
    if room["host_player_id"] != host_player_id:
        raise HTTPException(status_code=403, detail="not_host")

    game_id = room["game_id"]
    cfg = room.get("config", {})
    n = int(cfg.get("n_items", 10))
    difficulty = cfg.get("difficulty", "normal")
    dataset = cfg.get("dataset", "countries")
    continent = cfg.get("continent") if cfg.get("continent") != "all" else None
    country_filter = cfg.get("country_filter") or None

    if game_id == "ordering":
        questions = generate_ordering_set(num_questions=n, continent=continent, difficulty=difficulty, dataset=dataset, country_filter=country_filter)
    elif game_id == "comparison":
        questions = generate_comparison_set(num_questions=n, continent=continent, difficulty=difficulty, dataset=dataset, country_filter=country_filter)
    elif game_id == "geostats":
        result = generate_geostats_set(num_questions=n, continent=continent, dataset=dataset, country_filter=country_filter)
        countries_lookup = result.get("countries_lookup", {})
        # Embed countries_lookup into each question so clients can render names
        questions = []
        for q in result.get("questions", []):
            qc = dict(q)
            qc["countries_lookup"] = countries_lookup
            questions.append(qc)
    elif game_id in _QUIZ_GAMES:
        questions = generate_quiz_set(num_questions=n, continent=continent)
    else:
        raise HTTPException(status_code=400, detail="invalid_game")

    if not questions:
        raise HTTPException(status_code=400, detail="not_enough_data")

    updated, error = start_room(code, host_player_id, questions)
    if error == "not_host":
        raise HTTPException(status_code=403, detail="not_host")
    if error:
        raise HTTPException(status_code=400, detail=error)

    return {"status": "playing"}


@router.get("/api/rooms/{code}/state")
async def api_room_state(code: str):
    room = get_room(code)
    if not room:
        raise HTTPException(status_code=404, detail="room_not_found")
    return {
        "room_code": room["room_code"],
        "game_id": room["game_id"],
        "status": room["status"],
        "host_player_id": room["host_player_id"],
        "config": room.get("config", {}),
        "players": room.get("players", []),
        "scores": room.get("scores", {}),
        "n_questions": len(room.get("questions", [])),
        "started_at": room.get("started_at", ""),
    }


@router.get("/api/rooms/{code}/questions")
async def api_room_questions(code: str, player_id: str = ""):
    """Return full questions including answers (client-side scoring for casual play)."""
    room = get_room(code)
    if not room:
        raise HTTPException(status_code=404, detail="room_not_found")
    if room["status"] not in ("playing", "finished"):
        raise HTTPException(status_code=400, detail="not_started")

    players = room.get("players", [])
    if player_id and not any(p["player_id"] == player_id for p in players):
        raise HTTPException(status_code=403, detail="not_participant")

    return {
        "questions": room.get("questions", []),
        "game_type": room["game_id"],
        "config": room.get("config", {}),
    }


class ScorePayload(BaseModel):
    player_id: str
    score: int
    total: int
    time_ms: int = 0


@router.post("/api/rooms/{code}/score")
async def api_submit_score(code: str, payload: ScorePayload):
    room = get_room(code)
    if not room:
        raise HTTPException(status_code=404, detail="room_not_found")
    if room["status"] not in ("playing", "finished"):
        raise HTTPException(status_code=400, detail="not_active")

    players = room.get("players", [])
    if not any(p["player_id"] == payload.player_id for p in players):
        raise HTTPException(status_code=403, detail="not_participant")

    submit_score(code, payload.player_id, payload.score, payload.total, payload.time_ms)
    return {"ok": True}
