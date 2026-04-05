"""Daily challenge rankings — scoring, rating, and leaderboards.

Manages a separate ranking category for the daily challenge:
  - Daily ranking:    today's participants ordered by score S
  - Monthly ranking:  calendar month aggregation with consistency bonus
  - Absolute ranking: all-time EMA rating with consistency bonus

Rating design principles:
  - Each day's score S is computed with the same formulas as regular games
  - A single perfect day cannot outrank sustained good play
  - Missing a day is not catastrophic, but consistency matters
  - Only logged-in users participate
"""

import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings
from services.scoring import (
    compute_quality,
    compute_attempt_score,
    get_tref,
    SCORED_GAMES,
    DEFAULT_TREF,
)

# ── Constants ────────────────────────────────────────────────────────────────

# EMA smoothing for absolute rating
ALPHA_DAILY = 0.12

# How many recent days to consider for consistency bonus
CONSISTENCY_WINDOW = 30

TOP_N = 50
_CACHE_TTL_SECONDS = 300  # 5 min


def _is_stale(item: Optional[dict]) -> bool:
    """Check if a cached ranking is stale or missing."""
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


# ── DynamoDB table accessors ─────────────────────────────────────────────────

def _daily_scores_table():
    return get_dynamodb_resource().Table(get_settings().table_name("daily_scores"))


def _lb_table():
    return get_dynamodb_resource().Table(get_settings().table_name("leaderboards_cache"))


def _users_table():
    return get_dynamodb_resource().Table(get_settings().table_name("users"))


# ── Username loader ──────────────────────────────────────────────────────────

def _load_usernames(user_ids: list[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    table = _users_table()
    result: dict[str, str] = {}
    for i in range(0, len(user_ids), 100):
        batch = user_ids[i : i + 100]
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


# ── Score computation for a daily challenge ──────────────────────────────────

def compute_daily_score(
    game_type: str,
    score: int,
    total: int,
    time_ms: int,
    num_questions: int,
    config: dict,
) -> dict:
    """Compute the daily challenge score S using the standard scoring engine.

    Returns dict with q, score_s, tpp, tref.
    """
    n = num_questions or total
    time_seconds = time_ms / 1000.0

    avg_score = config.get("avg_score")
    if avg_score is not None:
        try:
            avg_score = float(avg_score)
        except (ValueError, TypeError):
            avg_score = None

    q = compute_quality(game_type, score, total, avg_score=avg_score)
    tref = config.get("secs_per_item", DEFAULT_TREF.get(game_type, 15))
    score_s = compute_attempt_score(q, n, time_seconds, tref)
    tpp = time_seconds / n if n > 0 else 0.0

    return {
        "q": round(q, 6),
        "score_s": round(score_s, 4),
        "tpp": round(tpp, 4),
        "tref": round(tref, 2),
    }


# ── Save daily score ────────────────────────────────────────────────────────

def save_daily_score(
    user_id: str,
    username: str,
    date: str,
    game_type: str,
    score: int,
    total: int,
    time_ms: int,
    num_questions: int,
    config: dict,
) -> dict:
    """Compute and persist a daily challenge score.

    Returns the computed score details.
    """
    result = compute_daily_score(
        game_type=game_type,
        score=score,
        total=total,
        time_ms=time_ms,
        num_questions=num_questions,
        config=config,
    )

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": user_id,
        "date": date,
        "username": username,
        "game_type": game_type,
        "score": score,
        "total": total,
        "time_ms": time_ms,
        "num_questions": num_questions,
        "q": Decimal(str(result["q"])),
        "score_s": Decimal(str(result["score_s"])),
        "tpp": Decimal(str(result["tpp"])),
        "tref": Decimal(str(result["tref"])),
        "created_at": now,
    }
    _daily_scores_table().put_item(Item=item)
    return result


# ── Query helpers ────────────────────────────────────────────────────────────

def get_user_daily_scores(user_id: str, limit: int = 90) -> list[dict]:
    """Get recent daily scores for a user (newest first)."""
    from boto3.dynamodb.conditions import Key

    resp = _daily_scores_table().query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [{
        "date": item["date"],
        "game_type": item.get("game_type", ""),
        "score": int(item.get("score", 0)),
        "total": int(item.get("total", 0)),
        "q": float(item.get("q", 0)),
        "score_s": float(item.get("score_s", 0)),
        "tpp": float(item.get("tpp", 0)),
    } for item in resp.get("Items", [])]


def get_user_daily_stats(user_id: str) -> dict:
    """Return total daily challenges played, current streak, and best score_s."""
    from boto3.dynamodb.conditions import Key

    items: list[dict] = []
    resp = _daily_scores_table().query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
    )
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = _daily_scores_table().query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))

    total = len(items)
    best_score_s = max((float(it.get("score_s", 0)) for it in items), default=0)

    # Current streak: consecutive days from today backwards
    today = datetime.now(timezone.utc).date()
    played_dates = sorted({it["date"] for it in items if it.get("date")}, reverse=True)
    streak = 0
    expected = today
    for d_str in played_dates:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d == expected:
            streak += 1
            expected = d - timedelta(days=1)
        elif d < expected:
            break

    return {"total": total, "streak": streak, "best_score_s": round(best_score_s, 1)}


def get_daily_leaderboard(date: str) -> list[dict]:
    """Get all scores for a specific date, ordered by score_s descending."""
    from boto3.dynamodb.conditions import Key

    resp = _daily_scores_table().query(
        IndexName="date-score-index",
        KeyConditionExpression=Key("date").eq(date),
        ScanIndexForward=False,
    )
    items = resp.get("Items", [])
    # Paginate if needed
    while "LastEvaluatedKey" in resp:
        resp = _daily_scores_table().query(
            IndexName="date-score-index",
            KeyConditionExpression=Key("date").eq(date),
            ScanIndexForward=False,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))

    # Resolve usernames from users table (daily_scores may lack username field)
    user_ids = list({item["user_id"] for item in items})
    usernames = _load_usernames(user_ids)

    entries = []
    for i, item in enumerate(items, 1):
        uid = item["user_id"]
        uname = usernames.get(uid, "")
        if not uname:
            continue  # skip entries without a resolvable username
        s = Decimal(str(round(float(item.get("score_s", 0)), 4)))
        entries.append({
            "rank": i,
            "user_id": uid,
            "username": uname,
            "value": s,
            "score_s": s,
            "q": Decimal(str(round(float(item.get("q", 0)), 6))),
            "game_type": item.get("game_type", ""),
        })

    # Re-rank after filtering
    for i, e in enumerate(entries, 1):
        e["rank"] = i

    return entries


# ── Scan all daily scores ───────────────────────────────────────────────────

def _scan_all_daily_scores() -> list[dict]:
    """Full scan of daily_scores table."""
    table = _daily_scores_table()
    items: list[dict] = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


# ── Monthly ranking ──────────────────────────────────────────────────────────

def _days_in_month(year: int, month: int) -> int:
    """Return number of days in a calendar month."""
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    return (next_month - first).days


def rebuild_monthly_ranking(year: int, month: int) -> int:
    """Build ranking for a specific calendar month.

    Monthly rating formula:
      R_month = avg_score * consistency_bonus

    Where:
      avg_score = average of daily S values in the month
      consistency_bonus = 1 + 0.5 * (days_played / days_in_month)^0.7

    This means:
      - Playing every day of a 30-day month gives bonus = 1.5
      - Playing 20/30 days gives bonus ≈ 1.38
      - Playing 10/30 days gives bonus ≈ 1.22
      - Playing 1/30 days gives bonus ≈ 1.03

    A user who plays 1 day with a perfect score (S=677) gets:
      677 * 1.03 = 697

    A user who plays 10 days with avg S=400 gets:
      400 * 1.22 = 488

    A user who plays 25 days with avg S=350 gets:
      350 * 1.45 = 508

    So consistent play is rewarded but quality still matters significantly.

    Eligibility: at least 3 days played in the month.
    """
    month_prefix = f"{year:04d}-{month:02d}-"
    total_days = _days_in_month(year, month)

    all_scores = _scan_all_daily_scores()
    month_scores = [s for s in all_scores if s.get("date", "").startswith(month_prefix)]

    if not month_scores:
        return 0

    # Group by user
    user_scores: dict[str, list[float]] = defaultdict(list)
    for s in month_scores:
        uid = s.get("user_id", "")
        ss = float(s.get("score_s", 0))
        user_scores[uid].append(ss)

    user_ids = list(user_scores.keys())
    usernames = _load_usernames(user_ids)

    entries: list[dict] = []
    for uid, scores in user_scores.items():
        days_played = len(scores)
        if days_played < 3:
            continue

        avg_s = sum(scores) / len(scores)
        ratio = days_played / total_days
        consistency_bonus = 1 + 0.5 * (ratio ** 0.7)
        rating = avg_s * consistency_bonus

        entries.append({
            "user_id": uid,
            "username": usernames.get(uid, "???"),
            "value": Decimal(str(round(rating, 4))),
            "avg_score": Decimal(str(round(avg_s, 4))),
            "days_played": days_played,
            "days_total": total_days,
            "consistency_bonus": Decimal(str(round(consistency_bonus, 4))),
        })

    entries.sort(key=lambda e: float(e["value"]), reverse=True)
    for i, e in enumerate(entries[:TOP_N], 1):
        e["rank"] = i

    month_key = f"{year:04d}-{month:02d}"
    now = datetime.now(timezone.utc).isoformat()
    _lb_table().put_item(Item={
        "leaderboard_id": f"daily-monthly#{month_key}#ranking",
        "scope": "daily-monthly",
        "game_type": "daily",
        "metric": "ranking",
        "month_key": month_key,
        "entries": entries[:TOP_N],
        "updated_at": now,
    })
    return 1


# ── Absolute ranking ────────────────────────────────────────────────────────

def rebuild_absolute_ranking() -> int:
    """Build all-time daily challenge ranking.

    Absolute rating formula:
      R_abs = ema_rating * consistency_bonus

    Where:
      ema_rating = Exponential Moving Average of daily scores
                   (chronological order, α=0.12)
                   Decayed for each missed day: R = R * decay_factor
      decay_factor = 0.995 per missed day (very gentle decay)
      consistency_bonus = 1 + 0.4 * (days_played / days_in_window)^0.6

    The window for consistency is the last 30 days.

    EMA processes days in chronological order:
      - For each played day: R = (1-α)*R + α*S
      - For each missed day (within active period): R = R * 0.995

    This ensures:
      - Sustained play builds a strong rating
      - A single great day can't dominate
      - Missing days causes gentle drift, not cliff-drop
      - Recent performance matters more (EMA recency)

    Eligibility: at least 5 days played total.
    """
    all_scores = _scan_all_daily_scores()
    if not all_scores:
        return 0

    # Group by user, sorted by date
    user_scores: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for s in all_scores:
        uid = s.get("user_id", "")
        date = s.get("date", "")
        ss = float(s.get("score_s", 0))
        user_scores[uid].append((date, ss))

    for uid in user_scores:
        user_scores[uid].sort(key=lambda x: x[0])

    # Consistency window
    today = datetime.now(timezone.utc)
    window_start = (today - timedelta(days=CONSISTENCY_WINDOW)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    user_ids = list(user_scores.keys())
    usernames = _load_usernames(user_ids)

    entries: list[dict] = []
    for uid, scores in user_scores.items():
        total_days = len(scores)
        if total_days < 5:
            continue

        # Compute EMA with decay for missed days
        ema = 0.0
        prev_date = None
        for date_str, score_s in scores:
            if prev_date is not None:
                d1 = datetime.strptime(prev_date, "%Y-%m-%d")
                d2 = datetime.strptime(date_str, "%Y-%m-%d")
                gap = (d2 - d1).days - 1
                if gap > 0:
                    # Decay for missed days (cap at 60 to avoid extreme decay)
                    decay_days = min(gap, 60)
                    ema *= 0.995 ** decay_days

            ema = (1 - ALPHA_DAILY) * ema + ALPHA_DAILY * score_s
            prev_date = date_str

        # Decay from last played day to today
        if prev_date:
            d_last = datetime.strptime(prev_date, "%Y-%m-%d")
            gap_to_today = (today - d_last.replace(tzinfo=timezone.utc)).days
            if gap_to_today > 0:
                decay_days = min(gap_to_today, 60)
                ema *= 0.995 ** decay_days

        # Consistency bonus (last 30 days)
        recent_days = sum(
            1 for d, _ in scores if d >= window_start and d <= today_str
        )
        ratio = recent_days / CONSISTENCY_WINDOW
        consistency_bonus = 1 + 0.4 * (ratio ** 0.6)

        rating = ema * consistency_bonus

        entries.append({
            "user_id": uid,
            "username": usernames.get(uid, "???"),
            "value": Decimal(str(round(rating, 4))),
            "ema_rating": Decimal(str(round(ema, 4))),
            "total_days": total_days,
            "recent_days": recent_days,
            "consistency_bonus": Decimal(str(round(consistency_bonus, 4))),
        })

    entries.sort(key=lambda e: float(e["value"]), reverse=True)
    for i, e in enumerate(entries[:TOP_N], 1):
        e["rank"] = i

    now = datetime.now(timezone.utc).isoformat()
    _lb_table().put_item(Item={
        "leaderboard_id": "daily-absolute#all#ranking",
        "scope": "daily-absolute",
        "game_type": "daily",
        "metric": "ranking",
        "entries": entries[:TOP_N],
        "updated_at": now,
    })
    return 1


# ── Daily ranking (today) ───────────────────────────────────────────────────

def rebuild_daily_ranking(date: Optional[str] = None) -> int:
    """Materialize today's (or a specific day's) daily challenge ranking.

    This is simply the day's scores sorted by score_s descending.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entries = get_daily_leaderboard(date)
    if not entries:
        return 0

    for i, e in enumerate(entries[:TOP_N], 1):
        e["rank"] = i

    now = datetime.now(timezone.utc).isoformat()
    _lb_table().put_item(Item={
        "leaderboard_id": f"daily-day#{date}#ranking",
        "scope": "daily-day",
        "game_type": "daily",
        "metric": "ranking",
        "date": date,
        "entries": entries[:TOP_N],
        "updated_at": now,
    })
    return 1


# ── Rebuild all ──────────────────────────────────────────────────────────────

def rebuild_all_daily_rankings() -> dict:
    """Rebuild all daily challenge rankings."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    daily_count = rebuild_daily_ranking(today)
    monthly_count = rebuild_monthly_ranking(now.year, now.month)
    absolute_count = rebuild_absolute_ranking()

    return {
        "daily": daily_count,
        "monthly": monthly_count,
        "absolute": absolute_count,
    }


# ── Public getters ───────────────────────────────────────────────────────────

def get_daily_day_ranking(date: Optional[str] = None) -> Optional[dict]:
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lid = f"daily-day#{date}#ranking"
    resp = _lb_table().get_item(Key={"leaderboard_id": lid})
    item = resp.get("Item")
    if _is_stale(item):
        rebuild_daily_ranking(date)
        resp = _lb_table().get_item(Key={"leaderboard_id": lid})
        item = resp.get("Item")
    return item


def get_daily_monthly_ranking(month_key: Optional[str] = None) -> Optional[dict]:
    if not month_key:
        now = datetime.now(timezone.utc)
        month_key = f"{now.year:04d}-{now.month:02d}"
    lid = f"daily-monthly#{month_key}#ranking"
    resp = _lb_table().get_item(Key={"leaderboard_id": lid})
    item = resp.get("Item")
    if _is_stale(item):
        year, month = int(month_key[:4]), int(month_key[5:7])
        rebuild_monthly_ranking(year, month)
        resp = _lb_table().get_item(Key={"leaderboard_id": lid})
        item = resp.get("Item")
    return item


def get_daily_absolute_ranking() -> Optional[dict]:
    resp = _lb_table().get_item(Key={"leaderboard_id": "daily-absolute#all#ranking"})
    item = resp.get("Item")
    if _is_stale(item):
        rebuild_absolute_ranking()
        resp = _lb_table().get_item(Key={"leaderboard_id": "daily-absolute#all#ranking"})
        item = resp.get("Item")
    return item


def get_user_daily_ranking_position(
    user_id: str,
    scope: str = "daily-day",
    date_or_month: Optional[str] = None,
) -> Optional[int]:
    """Return the user's 1-based position in a daily ranking, or None."""
    if scope == "daily-day":
        lb = get_daily_day_ranking(date_or_month)
    elif scope == "daily-monthly":
        lb = get_daily_monthly_ranking(date_or_month)
    elif scope == "daily-absolute":
        lb = get_daily_absolute_ranking()
    else:
        return None

    if not lb:
        return None

    for entry in lb.get("entries", []):
        if entry.get("user_id") == user_id:
            return int(entry.get("rank", 0))
    return None
