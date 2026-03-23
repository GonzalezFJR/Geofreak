"""Tournaments service — DynamoDB CRUD for geofreak_tournaments + geofreak_tournament_rounds.

Tables:
  tournaments:       PK = tournament_id (HASH)
  tournament_rounds: PK = tournament_id (HASH), SK = round_id (RANGE)

Lifecycle: waiting → active → finished | expired | cancelled
Round lifecycle: pending → active → finished
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from boto3.dynamodb.conditions import Key

from core.aws import get_dynamodb_resource
from core.config import get_settings
from services.quiz import generate_ordering_set, generate_comparison_set

import random

_TOURNAMENT_EXPIRY_HOURS = 24


def _t_table():
    return get_dynamodb_resource().Table(get_settings().table_name("tournaments"))


def _r_table():
    return get_dynamodb_resource().Table(get_settings().table_name("tournament_rounds"))


# ── Tournament CRUD ──────────────────────────────────────────────────────────

def create_tournament(
    created_by: str,
    username: str,
    number_of_rounds: int,
    config: dict,
) -> dict:
    """Create a tournament in 'waiting' status."""
    now = datetime.now(timezone.utc)
    tid = str(uuid.uuid4())
    item = {
        "tournament_id": tid,
        "created_by": created_by,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=_TOURNAMENT_EXPIRY_HOURS)).isoformat(),
        "status": "waiting",
        "format": "sequential",
        "number_of_rounds": number_of_rounds,
        "config": config,
        "current_round": 0,
        "scoreboard": {},             # {user_id: total_score}
        "players": [created_by],
        "player_usernames": {created_by: username},
        "last_activity_at": now.isoformat(),
    }
    _t_table().put_item(Item=item)
    return item


def get_tournament(tournament_id: str) -> Optional[dict]:
    resp = _t_table().get_item(Key={"tournament_id": tournament_id})
    return resp.get("Item")


def get_waiting_tournaments() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    resp = _t_table().scan(
        FilterExpression="#s = :s AND expires_at > :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "waiting", ":now": now},
    )
    return resp.get("Items", [])


def join_tournament(tournament_id: str, user_id: str, username: str) -> Optional[dict]:
    """Add a player to a waiting tournament."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        _t_table().update_item(
            Key={"tournament_id": tournament_id},
            UpdateExpression=(
                "SET scoreboard.#uid = :zero, player_usernames.#uid = :uname, "
                "last_activity_at = :now"
            ),
            ConditionExpression="#s = :waiting AND NOT contains(players, :uid)",
            ExpressionAttributeNames={"#s": "status", "#uid": user_id},
            ExpressionAttributeValues={
                ":waiting": "waiting",
                ":zero": 0,
                ":uid": user_id,
                ":uname": username,
                ":now": now,
            },
        )
        _t_table().update_item(
            Key={"tournament_id": tournament_id},
            UpdateExpression="SET players = list_append(players, :pl)",
            ExpressionAttributeValues={":pl": [user_id]},
        )
        return get_tournament(tournament_id)
    except _t_table().meta.client.exceptions.ConditionalCheckFailedException:
        return None


def start_tournament(tournament_id: str) -> Optional[dict]:
    """Move from waiting to active."""
    now = datetime.now(timezone.utc).isoformat()
    resp = _t_table().update_item(
        Key={"tournament_id": tournament_id},
        UpdateExpression="SET #s = :active, current_round = :one, last_activity_at = :now",
        ConditionExpression="#s = :waiting",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":active": "active", ":waiting": "waiting", ":one": 1, ":now": now},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def advance_round(tournament_id: str, new_round: int) -> Optional[dict]:
    now = datetime.now(timezone.utc).isoformat()
    resp = _t_table().update_item(
        Key={"tournament_id": tournament_id},
        UpdateExpression="SET current_round = :r, last_activity_at = :now",
        ExpressionAttributeValues={":r": new_round, ":now": now},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def update_scoreboard(tournament_id: str, user_id: str, add_score: int) -> Optional[dict]:
    """Atomically add score to a player's total."""
    resp = _t_table().update_item(
        Key={"tournament_id": tournament_id},
        UpdateExpression="SET scoreboard.#uid = scoreboard.#uid + :score",
        ExpressionAttributeNames={"#uid": user_id},
        ExpressionAttributeValues={":score": add_score},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def finish_tournament(tournament_id: str) -> Optional[dict]:
    now = datetime.now(timezone.utc).isoformat()
    resp = _t_table().update_item(
        Key={"tournament_id": tournament_id},
        UpdateExpression="SET #s = :finished, last_activity_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":finished": "finished", ":now": now},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def cancel_tournament(tournament_id: str) -> Optional[dict]:
    resp = _t_table().update_item(
        Key={"tournament_id": tournament_id},
        UpdateExpression="SET #s = :cancelled",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":cancelled": "cancelled"},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


# ── Tournament Rounds ────────────────────────────────────────────────────────

def create_round(
    tournament_id: str,
    round_number: int,
    game_type: str,
    config: dict,
    questions: list[dict],
    players: list[str],
) -> dict:
    """Create a new round for a tournament."""
    now = datetime.now(timezone.utc).isoformat()
    rid = f"round_{round_number}"
    item = {
        "tournament_id": tournament_id,
        "round_id": rid,
        "round_number": round_number,
        "game_type": game_type,
        "config": config,
        "questions": questions,
        "started_at": now,
        "finished_at": "",
        "status": "active",
        "round_scores": {uid: 0 for uid in players},        # {user_id: score}
        "round_progress": {uid: 0 for uid in players},      # {user_id: q_index}
        "player_finished": {uid: False for uid in players},  # {user_id: bool}
    }
    _r_table().put_item(Item=item)
    return item


def get_round(tournament_id: str, round_number: int) -> Optional[dict]:
    rid = f"round_{round_number}"
    resp = _r_table().get_item(Key={"tournament_id": tournament_id, "round_id": rid})
    return resp.get("Item")


def get_all_rounds(tournament_id: str) -> list[dict]:
    resp = _r_table().query(
        KeyConditionExpression=Key("tournament_id").eq(tournament_id),
    )
    items = resp.get("Items", [])
    items.sort(key=lambda r: int(r.get("round_number", 0)))
    return items


def update_round_progress(
    tournament_id: str,
    round_number: int,
    user_id: str,
    question_index: int,
    score: int,
) -> Optional[dict]:
    rid = f"round_{round_number}"
    resp = _r_table().update_item(
        Key={"tournament_id": tournament_id, "round_id": rid},
        UpdateExpression=(
            "SET round_scores.#uid = :score, round_progress.#uid = :qi"
        ),
        ExpressionAttributeNames={"#uid": user_id},
        ExpressionAttributeValues={":score": score, ":qi": question_index},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def mark_round_player_finished(
    tournament_id: str,
    round_number: int,
    user_id: str,
    score: int,
) -> Optional[dict]:
    rid = f"round_{round_number}"
    resp = _r_table().update_item(
        Key={"tournament_id": tournament_id, "round_id": rid},
        UpdateExpression=(
            "SET player_finished.#uid = :true, round_scores.#uid = :score"
        ),
        ExpressionAttributeNames={"#uid": user_id},
        ExpressionAttributeValues={":true": True, ":score": score},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def finish_round(tournament_id: str, round_number: int) -> Optional[dict]:
    rid = f"round_{round_number}"
    now = datetime.now(timezone.utc).isoformat()
    resp = _r_table().update_item(
        Key={"tournament_id": tournament_id, "round_id": rid},
        UpdateExpression="SET #s = :finished, finished_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":finished": "finished", ":now": now},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def all_round_players_finished(rnd: dict, players: list[str]) -> bool:
    finished = rnd.get("player_finished", {})
    return all(finished.get(pid, False) for pid in players)


# ── Question generation for rounds ──────────────────────────────────────────

def generate_round_questions(game_type: str, config: dict) -> list[dict]:
    """Generate questions for a tournament round."""
    num = config.get("num_questions", 10)
    continent = config.get("continent")
    if continent == "all":
        continent = None

    if game_type == "ordering":
        return generate_ordering_set(num_questions=num, continent=continent)
    else:
        return generate_comparison_set(num_questions=num, continent=continent)


def pick_round_game_type(config: dict) -> str:
    """Pick a random game type for a round from the allowed types."""
    allowed = config.get("game_types", ["ordering", "comparison"])
    return random.choice(allowed)
