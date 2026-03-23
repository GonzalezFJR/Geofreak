"""Match & match_players repositories — DynamoDB persistence."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings


def _matches_table():
    return get_dynamodb_resource().Table(get_settings().table_name("matches"))


def _match_players_table():
    return get_dynamodb_resource().Table(get_settings().table_name("match_players"))


# ── Matches ──────────────────────────────────────────────────────────────────

def create_match(
    mode: str,
    game_type: str,
    config: dict,
    total_players: int = 1,
) -> dict:
    """Create a new match record. Returns the item."""
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "match_id": str(uuid.uuid4()),
        "mode": mode,               # "solo", "duel", "tournament_round", "test"
        "game_type": game_type,      # "ordering", "comparison", "flags", etc.
        "created_at": now,
        "finished_at": "",
        "status": "in_progress",
        "config": config,
        "winner_id": "",
        "total_players": total_players,
        "duration_ms": 0,
    }
    _matches_table().put_item(Item=item)
    return item


def finish_match(
    match_id: str,
    winner_id: str = "",
    duration_ms: int = 0,
) -> Optional[dict]:
    """Mark a match as finished."""
    now = datetime.now(timezone.utc).isoformat()
    resp = _matches_table().update_item(
        Key={"match_id": match_id},
        UpdateExpression="SET #s = :s, finished_at = :fa, winner_id = :w, duration_ms = :d",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "finished",
            ":fa": now,
            ":w": winner_id,
            ":d": duration_ms,
        },
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def get_match(match_id: str) -> Optional[dict]:
    resp = _matches_table().get_item(Key={"match_id": match_id})
    return resp.get("Item")


# ── Match Players ────────────────────────────────────────────────────────────

def save_match_player(
    match_id: str,
    user_id: str,
    score: int,
    rank: int = 1,
    answers_summary: dict | None = None,
    accuracy: float = 0.0,
    time_spent_ms: int = 0,
    rating_delta: int = 0,
) -> dict:
    """Save a player's result for a match."""
    item = {
        "match_id": match_id,
        "user_id": user_id,
        "score": score,
        "rank": rank,
        "answers_summary": answers_summary or {},
        "accuracy": str(accuracy),
        "time_spent_ms": time_spent_ms,
        "rating_delta": rating_delta,
    }
    _match_players_table().put_item(Item=item)
    return item


def get_match_players(match_id: str) -> list[dict]:
    from boto3.dynamodb.conditions import Key
    resp = _match_players_table().query(
        KeyConditionExpression=Key("match_id").eq(match_id),
    )
    return resp.get("Items", [])
