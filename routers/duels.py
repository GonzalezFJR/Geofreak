"""Duels router — REST endpoints + WebSocket for real-time PvP."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.auth import get_current_user, get_optional_user
from core.i18n import get_lang, t
from core.templates import templates
from core.websocket_manager import manager
from services.auth import decode_token
from services.duels import (
    all_players_finished,
    cancel_duel,
    create_duel,
    finish_duel,
    get_duel,
    get_waiting_duels,
    join_duel,
    mark_player_finished,
    set_creator_username,
    update_progress,
)
from services.matches import create_match, finish_match, save_match_player
from services.quiz import generate_comparison_set, generate_ordering_set
from services.analytics import track
from services.user_stats import record_match_result
from services.users import get_user_by_id

router = APIRouter(tags=["duels"])


# ── Pages ────────────────────────────────────────────────────────────────────

@router.get("/duels")
async def duels_lobby_page(request=None, user: Optional[dict] = Depends(get_optional_user)):
    from starlette.requests import Request
    if request is None:
        request = Request
    lang = get_lang(request)
    waiting = get_waiting_duels() if user else []
    return templates.TemplateResponse("duels/lobby.html", {
        "request": request,
        "user": user,
        "lang": lang,
        "waiting_duels": waiting,
    })


@router.get("/duels/{duel_id}")
async def duel_play_page(duel_id: str, request=None, user: dict = Depends(get_current_user)):
    from starlette.requests import Request
    lang = get_lang(request)
    duel = get_duel(duel_id)
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    if user["user_id"] not in duel.get("players", []):
        raise HTTPException(status_code=403, detail="Not a participant")
    if duel["status"] == "finished":
        return templates.TemplateResponse("duels/results.html", {
            "request": request,
            "user": user,
            "lang": lang,
            "duel": duel,
        })
    return templates.TemplateResponse("duels/play.html", {
        "request": request,
        "user": user,
        "lang": lang,
        "duel": duel,
    })


# ── REST API ─────────────────────────────────────────────────────────────────

class CreateDuelPayload(BaseModel):
    game_type: str          # "ordering" or "comparison"
    num_questions: int = 10
    continent: str = "all"


@router.post("/api/duels/create")
async def api_create_duel(payload: CreateDuelPayload, user: dict = Depends(get_current_user)):
    if payload.game_type not in ("ordering", "comparison"):
        raise HTTPException(status_code=400, detail="Invalid game type")
    if payload.num_questions < 3 or payload.num_questions > 20:
        raise HTTPException(status_code=400, detail="Questions must be 3-20")

    # Generate shared question set
    if payload.game_type == "ordering":
        questions = generate_ordering_set(
            num_questions=payload.num_questions,
            continent=payload.continent if payload.continent != "all" else None,
        )
    else:
        questions = generate_comparison_set(
            num_questions=payload.num_questions,
            continent=payload.continent if payload.continent != "all" else None,
        )

    if not questions:
        raise HTTPException(status_code=400, detail="Not enough data")

    config = {
        "num_questions": payload.num_questions,
        "continent": payload.continent,
    }
    duel = create_duel(
        created_by=user["user_id"],
        game_type=payload.game_type,
        config=config,
        questions=questions,
    )
    # Set creator username and initialize scores
    set_creator_username(duel["duel_id"], user["user_id"], user["username"])

    track("duel_created", {"duel_id": duel["duel_id"], "user_id": user["user_id"], "game_type": payload.game_type})
    return {"duel_id": duel["duel_id"], "status": "waiting"}


@router.post("/api/duels/{duel_id}/join")
async def api_join_duel(duel_id: str, user: dict = Depends(get_current_user)):
    duel = get_duel(duel_id)
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    if duel["status"] != "waiting":
        raise HTTPException(status_code=400, detail="Duel is not waiting for players")
    if user["user_id"] in duel.get("players", []):
        raise HTTPException(status_code=400, detail="Already in this duel")

    updated = join_duel(duel_id, user["user_id"], user["username"])
    if not updated:
        raise HTTPException(status_code=400, detail="Could not join duel")

    # Notify other players via WebSocket
    await manager.broadcast_all(duel_id, {
        "type": "player_joined",
        "user_id": user["user_id"],
        "username": user["username"],
        "players": updated.get("players", []),
        "player_usernames": updated.get("player_usernames", {}),
    })

    track("duel_joined", {"duel_id": duel_id, "user_id": user["user_id"]})
    return {"duel_id": duel_id, "status": "active"}


@router.post("/api/duels/{duel_id}/cancel")
async def api_cancel_duel(duel_id: str, user: dict = Depends(get_current_user)):
    duel = get_duel(duel_id)
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    if duel["created_by"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    if duel["status"] not in ("waiting", "active"):
        raise HTTPException(status_code=400, detail="Cannot cancel this duel")

    cancel_duel(duel_id)
    await manager.broadcast_all(duel_id, {"type": "duel_cancelled"})
    return {"cancelled": True}


@router.get("/api/duels/waiting")
async def api_waiting_duels(user: dict = Depends(get_current_user)):
    duels = get_waiting_duels()
    return [
        {
            "duel_id": d["duel_id"],
            "game_type": d["game_type"],
            "config": d.get("config", {}),
            "created_by": d["created_by"],
            "creator_username": d.get("player_usernames", {}).get(d["created_by"], "?"),
            "created_at": d["created_at"],
            "num_questions": d.get("config", {}).get("num_questions", 10),
        }
        for d in duels
        if d["created_by"] != user["user_id"]
    ]


@router.get("/api/duels/{duel_id}")
async def api_get_duel(duel_id: str, user: dict = Depends(get_current_user)):
    duel = get_duel(duel_id)
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    # Don't expose questions with answers to the client
    safe_duel = {
        "duel_id": duel["duel_id"],
        "status": duel["status"],
        "game_type": duel["game_type"],
        "config": duel.get("config", {}),
        "players": duel.get("players", []),
        "player_usernames": duel.get("player_usernames", {}),
        "current_scores": _int_scores(duel.get("current_scores", {})),
        "current_progress": _int_progress(duel.get("current_progress", {})),
        "player_finished": duel.get("player_finished", {}),
        "created_by": duel["created_by"],
    }
    return safe_duel


@router.get("/api/duels/{duel_id}/questions")
async def api_duel_questions(duel_id: str, user: dict = Depends(get_current_user)):
    """Return the question set for a duel (only for participants of active duels)."""
    duel = get_duel(duel_id)
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    if user["user_id"] not in duel.get("players", []):
        raise HTTPException(status_code=403, detail="Not a participant")
    if duel["status"] not in ("active", "finished"):
        raise HTTPException(status_code=400, detail="Duel not started yet")

    questions = duel.get("questions", [])
    # For ordering: strip correct_order and correct_values from response
    # (validation happens server-side)
    if duel["game_type"] == "ordering":
        safe_questions = []
        for q in questions:
            safe_q = {
                "stat": q["stat"],
                "stat_info": q["stat_info"],
                "ascending": q["ascending"],
                "countries": q["countries"],
            }
            safe_questions.append(safe_q)
        return {"questions": safe_questions, "game_type": "ordering"}
    else:
        # Comparison: strip correct_iso and values
        safe_questions = []
        for q in questions:
            safe_q = {
                "stat": q["stat"],
                "stat_info": q["stat_info"],
                "countries": q["countries"],
            }
            safe_questions.append(safe_q)
        return {"questions": safe_questions, "game_type": "comparison"}


class AnswerPayload(BaseModel):
    question_index: int
    answer: str | list[str]  # ISO code or list of ISO codes (ordering)


@router.post("/api/duels/{duel_id}/answer")
async def api_submit_answer(duel_id: str, payload: AnswerPayload, user: dict = Depends(get_current_user)):
    """Submit an answer for a duel question. Server validates and updates."""
    duel = get_duel(duel_id)
    if not duel:
        raise HTTPException(status_code=404, detail="Duel not found")
    if duel["status"] != "active":
        raise HTTPException(status_code=400, detail="Duel not active")
    if user["user_id"] not in duel.get("players", []):
        raise HTTPException(status_code=403, detail="Not a participant")

    questions = duel.get("questions", [])
    qi = payload.question_index
    if qi < 0 or qi >= len(questions):
        raise HTTPException(status_code=400, detail="Invalid question index")

    q = questions[qi]
    correct = False

    if duel["game_type"] == "ordering":
        # answer is a list of ISO codes in player's order
        correct_order = q.get("correct_order", [])
        correct = payload.answer == correct_order
    else:
        # Comparison: answer is an ISO code
        correct = payload.answer == q.get("correct_iso", "")

    # Update score
    current_score = int(duel.get("current_scores", {}).get(user["user_id"], 0))
    if correct:
        current_score += 1

    updated = update_progress(duel_id, user["user_id"], qi + 1, current_score)

    # Build answer feedback
    feedback = {"correct": correct, "question_index": qi}
    if duel["game_type"] == "ordering":
        feedback["correct_order"] = q.get("correct_order", [])
        feedback["correct_values"] = q.get("correct_values", {})
    else:
        feedback["correct_iso"] = q.get("correct_iso", "")
        feedback["values"] = q.get("values", {})

    # Broadcast progress to opponent
    await manager.broadcast(duel_id, {
        "type": "opponent_progress",
        "user_id": user["user_id"],
        "question_index": qi + 1,
        "score": current_score,
    }, exclude=user["user_id"])

    # Check if player finished all questions
    is_last = (qi + 1) >= len(questions)
    if is_last:
        mark_player_finished(duel_id, user["user_id"], current_score)
        duel_updated = get_duel(duel_id)
        if duel_updated and all_players_finished(duel_updated):
            finish_duel(duel_id)
            await _persist_match_results(duel_updated)
            track("duel_finished", {"duel_id": duel_id, "scores": _int_scores(duel_updated.get("current_scores", {}))})
            await manager.broadcast_all(duel_id, {
                "type": "duel_finished",
                "scores": _int_scores(duel_updated.get("current_scores", {})),
                "player_usernames": duel_updated.get("player_usernames", {}),
            })
        else:
            await manager.broadcast(duel_id, {
                "type": "player_finished",
                "user_id": user["user_id"],
                "score": current_score,
            }, exclude=user["user_id"])

    feedback["is_last"] = is_last
    feedback["current_score"] = current_score
    feedback["total_answered"] = qi + 1
    return feedback


# ── WebSocket ────────────────────────────────────────────────────────────────

@router.websocket("/ws/duel/{duel_id}")
async def duel_websocket(websocket: WebSocket, duel_id: str):
    """WebSocket endpoint for real-time duel updates."""
    # Authenticate via cookie
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

    user_id = user["user_id"]

    # Verify user is participant
    duel = get_duel(duel_id)
    if not duel or user_id not in duel.get("players", []):
        await websocket.close(code=4003)
        return

    await manager.connect(duel_id, user_id, websocket)

    # Notify others
    await manager.broadcast(duel_id, {
        "type": "user_connected",
        "user_id": user_id,
        "username": user.get("username", ""),
        "connected_users": manager.get_connected_users(duel_id),
    }, exclude=user_id)

    try:
        while True:
            # Keep connection alive; actions go through REST
            data = await websocket.receive_text()
            # Client can send pings
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(duel_id, user_id)
        await manager.broadcast(duel_id, {
            "type": "user_disconnected",
            "user_id": user_id,
            "connected_users": manager.get_connected_users(duel_id),
        })


# ── Helpers ──────────────────────────────────────────────────────────────────

def _int_scores(scores: dict) -> dict:
    return {k: int(v) for k, v in scores.items()}


def _int_progress(progress: dict) -> dict:
    return {k: int(v) for k, v in progress.items()}


async def _persist_match_results(duel: dict) -> None:
    """Create match + match_players records and update user_stats."""
    game_type = duel.get("game_type", "ordering")
    config = duel.get("config", {})
    players = duel.get("players", [])
    scores = duel.get("current_scores", {})
    questions = duel.get("questions", [])
    total = len(questions)

    # Determine winner
    sorted_players = sorted(players, key=lambda p: int(scores.get(p, 0)), reverse=True)
    winner_id = sorted_players[0] if sorted_players else ""

    match = create_match(
        mode="duel",
        game_type=game_type,
        config=config,
        total_players=len(players),
    )
    finish_match(match_id=match["match_id"], winner_id=winner_id)

    for rank, pid in enumerate(sorted_players, 1):
        score = int(scores.get(pid, 0))
        accuracy = (score / total * 100) if total > 0 else 0
        save_match_player(
            match_id=match["match_id"],
            user_id=pid,
            score=score,
            rank=rank,
            accuracy=accuracy,
        )
        record_match_result(
            user_id=pid,
            game_type=game_type,
            score=score,
            total=total,
            accuracy=accuracy,
            time_ms=0,
            won=(pid == winner_id),
        )
