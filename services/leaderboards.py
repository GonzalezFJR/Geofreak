"""Leaderboard service — materialized rankings in DynamoDB."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings


# ── Helpers ──────────────────────────────────────────────────────────────────

_CACHE_TTL_SECONDS = 300  # 5 min

LEADERBOARD_TYPES = [
    {"scope": "global", "game_type": "all", "metric": "rating"},
    {"scope": "global", "game_type": "all", "metric": "total_matches"},
    {"scope": "global", "game_type": "all", "metric": "best_streak"},
]

# Per-game leaderboards are generated dynamically for each game_type
GAME_TYPES = [
    "flags", "outline",
    "map-challenge",
    "ordering", "comparison",
]

TOP_N = 50  # how many entries to store per leaderboard


def _lb_table():
    return get_dynamodb_resource().Table(get_settings().table_name("leaderboards_cache"))


def _stats_table():
    return get_dynamodb_resource().Table(get_settings().table_name("user_stats"))


def _users_table():
    return get_dynamodb_resource().Table(get_settings().table_name("users"))


def _make_id(scope: str, game_type: str, metric: str) -> str:
    return f"{scope}#{game_type}#{metric}"


def _is_stale(item: Optional[dict]) -> bool:
    if not item:
        return True
    updated = item.get("updated_at", "")
    if not updated:
        return True
    try:
        ts = datetime.fromisoformat(updated)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > _CACHE_TTL_SECONDS
    except (ValueError, TypeError):
        return True


# ── Username cache ───────────────────────────────────────────────────────────

def _load_usernames(user_ids: list[str]) -> dict[str, str]:
    """Batch-get usernames for a list of user_ids."""
    if not user_ids:
        return {}
    table = _users_table()
    result = {}
    # DynamoDB BatchGetItem allows max 100 keys
    for i in range(0, len(user_ids), 100):
        batch = user_ids[i:i + 100]
        resp = get_dynamodb_resource().batch_get_item(
            RequestItems={
                table.name: {
                    "Keys": [{"user_id": uid} for uid in batch],
                    "ProjectionExpression": "user_id, username",
                }
            }
        )
        for item in resp.get("Responses", {}).get(table.name, []):
            result[item["user_id"]] = item.get("username", "???")
    return result


# ── Build leaderboard ────────────────────────────────────────────────────────

def _scan_all_stats() -> list[dict]:
    """Full scan of user_stats table. Returns all items."""
    table = _stats_table()
    items = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def _build_global_leaderboard(all_stats: list[dict], metric: str, usernames: dict) -> list[dict]:
    """Build a sorted top-N list for a global metric."""
    entries = []
    for s in all_stats:
        uid = s["user_id"]
        if metric == "rating":
            value = int(s.get("rating", 1000))
        elif metric == "total_matches":
            value = int(s.get("total_matches", 0))
        elif metric == "best_streak":
            value = int(s.get("best_streak", 0))
        else:
            continue
        if metric == "total_matches" and value == 0:
            continue
        entries.append({
            "user_id": uid,
            "username": usernames.get(uid, "???"),
            "value": value,
        })

    # Sort descending
    entries.sort(key=lambda e: e["value"], reverse=True)
    # Assign ranks
    for i, e in enumerate(entries[:TOP_N], 1):
        e["rank"] = i

    return entries[:TOP_N]


def _build_game_leaderboard(all_stats: list[dict], game_type: str, usernames: dict) -> list[dict]:
    """Build a top-N list for best_score in a specific game."""
    entries = []
    for s in all_stats:
        uid = s["user_id"]
        by_game = s.get("stats_by_game") or {}
        game_stats = by_game.get(game_type)
        if not game_stats:
            continue
        best = int(game_stats.get("best_score", 0))
        if best == 0:
            continue
        entries.append({
            "user_id": uid,
            "username": usernames.get(uid, "???"),
            "value": best,
            "matches": int(game_stats.get("matches", 0)),
        })

    entries.sort(key=lambda e: e["value"], reverse=True)
    for i, e in enumerate(entries[:TOP_N], 1):
        e["rank"] = i

    return entries[:TOP_N]


def _save_leaderboard(leaderboard_id: str, scope: str, game_type: str,
                      metric: str, entries: list[dict]) -> dict:
    """Write a leaderboard to DynamoDB."""
    now = datetime.now(timezone.utc).isoformat()
    # Convert ints to Decimal for DynamoDB
    clean_entries = []
    for e in entries:
        clean = {k: (Decimal(str(v)) if isinstance(v, (int, float)) else v) for k, v in e.items()}
        clean_entries.append(clean)

    item = {
        "leaderboard_id": leaderboard_id,
        "scope": scope,
        "game_type": game_type,
        "metric": metric,
        "entries": clean_entries,
        "updated_at": now,
    }
    _lb_table().put_item(Item=item)
    return item


# ── Public API ───────────────────────────────────────────────────────────────

def rebuild_all_leaderboards() -> int:
    """Full rebuild of all leaderboards. Returns count of boards rebuilt."""
    all_stats = _scan_all_stats()
    if not all_stats:
        return 0

    # Collect all user_ids
    user_ids = list({s["user_id"] for s in all_stats})
    usernames = _load_usernames(user_ids)

    count = 0

    # Global boards
    for lb in LEADERBOARD_TYPES:
        lid = _make_id(lb["scope"], lb["game_type"], lb["metric"])
        entries = _build_global_leaderboard(all_stats, lb["metric"], usernames)
        _save_leaderboard(lid, lb["scope"], lb["game_type"], lb["metric"], entries)
        count += 1

    # Per-game boards
    for gt in GAME_TYPES:
        lid = _make_id("game", gt, "best_score")
        entries = _build_game_leaderboard(all_stats, gt, usernames)
        _save_leaderboard(lid, "game", gt, "best_score", entries)
        count += 1

    return count


def get_leaderboard(scope: str, game_type: str = "all", metric: str = "rating",
                    auto_rebuild: bool = True) -> Optional[dict]:
    """Get a leaderboard from cache. Auto-rebuild if stale."""
    lid = _make_id(scope, game_type, metric)
    resp = _lb_table().get_item(Key={"leaderboard_id": lid})
    item = resp.get("Item")

    if _is_stale(item) and auto_rebuild:
        rebuild_all_leaderboards()
        resp = _lb_table().get_item(Key={"leaderboard_id": lid})
        item = resp.get("Item")

    if not item:
        return None

    # Convert Decimals back to int for JSON serialization
    entries = item.get("entries", [])
    for e in entries:
        for k, v in e.items():
            if isinstance(v, Decimal):
                e[k] = int(v)

    item["entries"] = entries
    return item


def get_user_position(user_id: str, scope: str = "global", game_type: str = "all",
                      metric: str = "rating") -> Optional[int]:
    """Find a user's rank in a specific leaderboard. Returns rank (1-based) or None."""
    lb = get_leaderboard(scope, game_type, metric)
    if not lb:
        return None
    for entry in lb.get("entries", []):
        if entry.get("user_id") == user_id:
            return entry.get("rank")
    return None
