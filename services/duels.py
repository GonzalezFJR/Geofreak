"""Duels service — DynamoDB CRUD for geofreak_duels.

Table schema:
  PK = duel_id (HASH), no GSIs

Duel lifecycle: waiting → active → finished | expired | cancelled
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings


_DUEL_EXPIRY_HOURS = 8


def _table():
    return get_dynamodb_resource().Table(get_settings().table_name("duels"))


# ── Create ───────────────────────────────────────────────────────────────────

def create_duel(
    created_by: str,
    game_type: str,
    config: dict,
    questions: list[dict],
) -> dict:
    """Create a new duel in 'waiting' status. Returns the duel item."""
    now = datetime.now(timezone.utc)
    duel_id = str(uuid.uuid4())
    item = {
        "duel_id": duel_id,
        "match_id": "",              # set when duel starts
        "created_by": created_by,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=_DUEL_EXPIRY_HOURS)).isoformat(),
        "status": "waiting",         # waiting → active → finished/expired/cancelled
        "game_type": game_type,      # "ordering" or "comparison"
        "config": config,
        "questions": questions,       # shared question set
        "current_scores": {},         # {user_id: int}
        "current_progress": {},       # {user_id: int} — question index
        "players": [created_by],
        "player_usernames": {},       # {user_id: username}
        "player_finished": {},        # {user_id: bool}
        "last_activity_at": now.isoformat(),
    }
    _table().put_item(Item=item)
    return item


# ── Read ─────────────────────────────────────────────────────────────────────

def get_duel(duel_id: str) -> Optional[dict]:
    resp = _table().get_item(Key={"duel_id": duel_id})
    return resp.get("Item")


def get_active_duels_for_user(user_id: str) -> list[dict]:
    """Return duels where user is a player and status is waiting/active.
    Uses scan (acceptable for MVP with low duel count).
    """
    resp = _table().scan(
        FilterExpression="contains(players, :uid) AND #s IN (:s1, :s2)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":uid": user_id,
            ":s1": "waiting",
            ":s2": "active",
        },
    )
    return resp.get("Items", [])


def get_waiting_duels() -> list[dict]:
    """Return duels in 'waiting' status (for the lobby)."""
    now = datetime.now(timezone.utc).isoformat()
    resp = _table().scan(
        FilterExpression="#s = :s AND expires_at > :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "waiting", ":now": now},
    )
    return resp.get("Items", [])


# ── Join ─────────────────────────────────────────────────────────────────────

def join_duel(duel_id: str, user_id: str, username: str) -> Optional[dict]:
    """Add a player to a waiting duel and set status to 'active'."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        resp = _table().update_item(
            Key={"duel_id": duel_id},
            UpdateExpression=(
                "SET #s = :active, match_id = :mid, last_activity_at = :now, "
                "current_scores.#uid = :zero, current_progress.#uid = :zero, "
                "player_finished.#uid = :false, player_usernames.#uid = :uname"
            ),
            ConditionExpression="#s = :waiting AND NOT contains(players, :uid)",
            ExpressionAttributeNames={
                "#s": "status",
                "#uid": user_id,
            },
            ExpressionAttributeValues={
                ":active": "active",
                ":waiting": "waiting",
                ":mid": str(uuid.uuid4()),
                ":now": now,
                ":zero": 0,
                ":false": False,
                ":uid": user_id,
                ":uname": username,
            },
            ReturnValues="ALL_NEW",
        )
        # Also append user_id to players list
        _table().update_item(
            Key={"duel_id": duel_id},
            UpdateExpression="SET players = list_append(players, :pl)",
            ExpressionAttributeValues={":pl": [user_id]},
        )
        # Re-fetch to get updated players list
        return get_duel(duel_id)
    except _table().meta.client.exceptions.ConditionalCheckFailedException:
        return None


def set_creator_username(duel_id: str, user_id: str, username: str) -> None:
    """Set the creator's username and initial scores after creation."""
    _table().update_item(
        Key={"duel_id": duel_id},
        UpdateExpression=(
            "SET current_scores.#uid = :zero, current_progress.#uid = :zero, "
            "player_finished.#uid = :false, player_usernames.#uid = :uname"
        ),
        ExpressionAttributeNames={"#uid": user_id},
        ExpressionAttributeValues={
            ":zero": 0,
            ":false": False,
            ":uname": username,
        },
    )


# ── Progress ─────────────────────────────────────────────────────────────────

def update_progress(
    duel_id: str,
    user_id: str,
    question_index: int,
    score: int,
) -> Optional[dict]:
    """Update a player's progress and score."""
    now = datetime.now(timezone.utc).isoformat()
    resp = _table().update_item(
        Key={"duel_id": duel_id},
        UpdateExpression=(
            "SET current_scores.#uid = :score, current_progress.#uid = :qi, "
            "last_activity_at = :now"
        ),
        ExpressionAttributeNames={"#uid": user_id},
        ExpressionAttributeValues={
            ":score": score,
            ":qi": question_index,
            ":now": now,
        },
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def mark_player_finished(duel_id: str, user_id: str, score: int) -> Optional[dict]:
    """Mark a player as finished."""
    now = datetime.now(timezone.utc).isoformat()
    resp = _table().update_item(
        Key={"duel_id": duel_id},
        UpdateExpression=(
            "SET player_finished.#uid = :true, current_scores.#uid = :score, "
            "last_activity_at = :now"
        ),
        ExpressionAttributeNames={"#uid": user_id},
        ExpressionAttributeValues={
            ":true": True,
            ":score": score,
            ":now": now,
        },
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


# ── Finish ───────────────────────────────────────────────────────────────────

def finish_duel(duel_id: str) -> Optional[dict]:
    """Mark the duel as finished."""
    now = datetime.now(timezone.utc).isoformat()
    resp = _table().update_item(
        Key={"duel_id": duel_id},
        UpdateExpression="SET #s = :finished, last_activity_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":finished": "finished", ":now": now},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def cancel_duel(duel_id: str) -> Optional[dict]:
    """Cancel a waiting duel."""
    resp = _table().update_item(
        Key={"duel_id": duel_id},
        UpdateExpression="SET #s = :cancelled",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":cancelled": "cancelled"},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def all_players_finished(duel: dict) -> bool:
    """Check if every player has finished."""
    finished = duel.get("player_finished", {})
    players = duel.get("players", [])
    if len(players) < 2:
        return False
    return all(finished.get(pid, False) for pid in players)
