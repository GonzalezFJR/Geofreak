"""User stats repository — DynamoDB aggregated statistics per user."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings


def _table():
    return get_dynamodb_resource().Table(get_settings().table_name("user_stats"))


def get_user_stats(user_id: str) -> Optional[dict]:
    resp = _table().get_item(Key={"user_id": user_id})
    return resp.get("Item")


def ensure_user_stats(user_id: str) -> dict:
    """Get or create a default stats record."""
    existing = get_user_stats(user_id)
    if existing:
        return existing
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": user_id,
        "total_matches": 0,
        "total_wins": 0,
        "total_losses": 0,
        "total_tournaments": 0,
        "best_streak": 0,
        "current_streak": 0,
        "rating": 1000,
        "stats_by_game": {},
        "best_scores": {},
        "best_times": {},
        "updated_at": now,
    }
    _table().put_item(Item=item)
    return item


def record_match_result(
    user_id: str,
    game_type: str,
    score: int,
    total: int,
    accuracy: float,
    time_ms: int,
    won: bool = False,
) -> dict:
    """Update aggregated stats after a match finishes."""
    stats = ensure_user_stats(user_id)
    now = datetime.now(timezone.utc).isoformat()

    # Per-game stats
    by_game = stats.get("stats_by_game", {}) or {}
    game_stats = by_game.get(game_type, {
        "matches": 0,
        "total_score": 0,
        "best_score": 0,
        "total_accuracy": "0",
        "best_time_ms": 0,
    })
    game_stats["matches"] = int(game_stats.get("matches", 0)) + 1
    game_stats["total_score"] = int(game_stats.get("total_score", 0)) + score
    if score > int(game_stats.get("best_score", 0)):
        game_stats["best_score"] = score
    if time_ms > 0 and (int(game_stats.get("best_time_ms", 0)) == 0 or time_ms < int(game_stats.get("best_time_ms", 0))):
        game_stats["best_time_ms"] = time_ms
    by_game[game_type] = game_stats

    # Best scores
    best_scores = stats.get("best_scores", {}) or {}
    if score > int(best_scores.get(game_type, 0)):
        best_scores[game_type] = score

    # Streak
    current_streak = int(stats.get("current_streak", 0))
    best_streak = int(stats.get("best_streak", 0))
    if won:
        current_streak += 1
        if current_streak > best_streak:
            best_streak = current_streak
    else:
        current_streak = 0

    # Recent matches (keep last 20)
    recent = list(stats.get("recent_matches") or [])
    recent.insert(0, {
        "game_type": game_type,
        "score": score,
        "total": total,
        "accuracy": str(Decimal(str(round(accuracy, 4)))),
        "time_ms": time_ms,
        "won": won,
        "date": now,
    })
    recent = recent[:20]

    resp = _table().update_item(
        Key={"user_id": user_id},
        UpdateExpression=(
            "SET total_matches = total_matches + :one, "
            "total_wins = total_wins + :win, "
            "current_streak = :cs, "
            "best_streak = :bs, "
            "stats_by_game = :sbg, "
            "best_scores = :bsc, "
            "recent_matches = :rm, "
            "updated_at = :now"
        ),
        ExpressionAttributeValues={
            ":one": 1,
            ":win": 1 if won else 0,
            ":cs": current_streak,
            ":bs": best_streak,
            ":sbg": by_game,
            ":bsc": best_scores,
            ":rm": recent,
            ":now": now,
        },
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes", {})
