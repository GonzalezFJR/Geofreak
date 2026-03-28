"""Rooms service — DynamoDB CRUD for geofreak_rooms.

Room lifecycle: lobby → playing → finished | expired
Room codes: 8-char uppercase alphanumeric (e.g., "AB3X7K2M")
Players can be registered users or guests (identified by guest_id token).
Max 10 players per room. Rooms expire after 2 hours.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings

_ROOM_EXPIRY_HOURS = 2
MAX_PLAYERS = 10


def _to_decimal(obj):
    """Recursively convert float values to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_decimal(v) for v in obj]
    return obj
_CODE_CHARS = string.ascii_uppercase + string.digits


def _table():
    return get_dynamodb_resource().Table(get_settings().table_name("rooms"))


def generate_code() -> str:
    return "".join(random.choices(_CODE_CHARS, k=8))


# ── Create ────────────────────────────────────────────────────────────────────

def create_room(
    game_id: str,
    host_player_id: str,
    host_name: str,
    is_host_guest: bool,
    host_user_id: Optional[str],
    config: dict,
) -> dict:
    """Create a new room in 'lobby' status. Returns the room item."""
    now = datetime.now(timezone.utc)
    # Generate unique code (retry up to 5 times on collision)
    code = generate_code()
    for _ in range(4):
        if not get_room(code):
            break
        code = generate_code()

    item = {
        "room_code": code,
        "game_id": game_id,
        "status": "lobby",
        "host_player_id": host_player_id,
        "config": config,
        "questions": [],
        "players": [
            {
                "player_id": host_player_id,
                "name": host_name,
                "is_guest": is_host_guest,
                "user_id": host_user_id or "",
                "joined_at": now.isoformat(),
            }
        ],
        "scores": {},
        "created_at": now.isoformat(),
        "started_at": "",
        "expires_at": (now + timedelta(hours=_ROOM_EXPIRY_HOURS)).isoformat(),
    }
    _table().put_item(Item=item)
    return item


# ── Read ──────────────────────────────────────────────────────────────────────

def get_room(code: str) -> Optional[dict]:
    resp = _table().get_item(Key={"room_code": code.upper()})
    return resp.get("Item")


# ── Join ──────────────────────────────────────────────────────────────────────

def join_room(
    code: str,
    player_id: str,
    name: str,
    is_guest: bool,
    user_id: Optional[str],
) -> tuple[Optional[dict], str]:
    """Add a player to a lobby room.

    Returns (room, error_key) — error_key is '' on success.
    """
    room = get_room(code)
    if not room:
        return None, "not_found"
    now_iso = datetime.now(timezone.utc).isoformat()
    if room.get("expires_at", "") < now_iso:
        return None, "expired"
    if room["status"] != "lobby":
        return None, "already_started"

    players = room.get("players", [])
    # Already in room → return current state
    if any(p["player_id"] == player_id for p in players):
        return room, ""
    if len(players) >= MAX_PLAYERS:
        return None, "full"

    new_player = {
        "player_id": player_id,
        "name": name,
        "is_guest": is_guest,
        "user_id": user_id or "",
        "joined_at": now_iso,
    }
    _table().update_item(
        Key={"room_code": code.upper()},
        UpdateExpression="SET players = list_append(players, :p)",
        ExpressionAttributeValues={":p": [new_player]},
    )
    return get_room(code), ""


# ── Start ─────────────────────────────────────────────────────────────────────

def start_room(
    code: str,
    host_player_id: str,
    questions: list,
) -> tuple[Optional[dict], str]:
    """Mark room as playing and store the question set.

    Returns (room, error_key).
    """
    room = get_room(code)
    if not room:
        return None, "not_found"
    if room["host_player_id"] != host_player_id:
        return None, "not_host"
    if room["status"] != "lobby":
        return None, "already_started"

    now_iso = datetime.now(timezone.utc).isoformat()
    _table().update_item(
        Key={"room_code": code.upper()},
        UpdateExpression="SET #s = :playing, questions = :q, started_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":playing": "playing",
            ":q": _to_decimal(questions),
            ":now": now_iso,
        },
    )
    return get_room(code), ""


# ── Score ─────────────────────────────────────────────────────────────────────

def submit_score(
    code: str,
    player_id: str,
    score: int,
    total: int,
    time_ms: int,
) -> Optional[dict]:
    """Record a player's final score. Auto-finishes room if everyone submitted."""
    pct = round(score / total * 100) if total > 0 else 0
    score_item = {
        "score": score,
        "total": total,
        "pct": pct,
        "time_ms": time_ms,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    _table().update_item(
        Key={"room_code": code.upper()},
        UpdateExpression="SET scores.#pid = :s",
        ExpressionAttributeNames={"#pid": player_id},
        ExpressionAttributeValues={":s": score_item},
    )
    room = get_room(code)
    if room:
        players = room.get("players", [])
        scores = room.get("scores", {})
        if players and all(p["player_id"] in scores for p in players):
            _table().update_item(
                Key={"room_code": code.upper()},
                UpdateExpression="SET #s = :finished",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":finished": "finished"},
            )
            return get_room(code)
    return room
