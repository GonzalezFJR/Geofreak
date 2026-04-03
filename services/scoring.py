"""Scoring engine — unified scoring system for all GeoFreak games.

Converts every ranked attempt into a comparable score S, computes
percentiles per test, maintains per-test ratings R_test, and manages
configuration-specific records for map/relief games.
"""

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings

# ── Game classification ──────────────────────────────────────────────────────

# Binary games: q = correct / total
BINARY_GAMES = {"flags", "outline", "map-challenge", "relief-challenge", "comparison"}

# Scored games: per-question score 0..10, q = avg_score / 10
SCORED_GAMES = {"geostats", "ordering"}

# Games with configuration-specific records
RECORD_GAMES = {"map-challenge", "relief-challenge"}

# All 7 competitive game types
ALL_GAME_TYPES = BINARY_GAMES | SCORED_GAMES

# Default reference time per question (seconds)
DEFAULT_TREF = {
    "flags": 20,
    "outline": 20,
    "comparison": 20,
    "ordering": 20,
    "geostats": 20,
    "map-challenge": 6,
    "relief-challenge": 8,
}

# Rating update parameters
LAMBDA_RATING = 0.20
LAMBDA_SPAM = 0.05


# ── DynamoDB table accessors ─────────────────────────────────────────────────

def _attempts_table():
    return get_dynamodb_resource().Table(get_settings().table_name("ranked_attempts"))


def _ratings_table():
    return get_dynamodb_resource().Table(get_settings().table_name("test_ratings"))


def _records_table():
    return get_dynamodb_resource().Table(get_settings().table_name("records"))


# ── Key builders ─────────────────────────────────────────────────────────────

def build_test_key(game_type: str, config: dict, num_questions: int = 0) -> str:
    """Build a canonical test key from game type and configuration.

    Format:
      map-challenge:   {gt}:{dataset}:{continent}:{mode}:{category}:{n}
      relief-challenge: {gt}:{dataset}:{continent}:{mode}:{category}:{n}
      others:           {gt}:{dataset}:{continent}:{n}

    Where mode = click|type, category = all|relief|water|coast|...,
    dataset = countries|cities|us-states|..., continent = all|europe|...
    """
    dataset = config.get("dataset", "countries")
    continent = config.get("continent", "all")
    n = config.get("questions", config.get("num_questions", num_questions))
    if game_type in ("map-challenge", "relief-challenge"):
        mode = config.get("game_mode", config.get("mode", "click"))
        category = config.get("category", "all")
        return f"{game_type}:{dataset}:{continent}:{mode}:{category}:{n}"
    return f"{game_type}:{dataset}:{continent}:{n}"


def parse_test_key(test_key: str) -> dict:
    """Parse a test_key into its components."""
    parts = test_key.split(":")
    gt = parts[0]
    if gt in ("map-challenge", "relief-challenge") and len(parts) >= 6:
        return {
            "game_type": gt,
            "dataset": parts[1],
            "continent": parts[2],
            "mode": parts[3],
            "category": parts[4],
            "n": int(parts[5]) if parts[5].isdigit() else 0,
        }
    elif gt in ("map-challenge", "relief-challenge") and len(parts) == 5:
        # Legacy format without mode
        return {
            "game_type": gt,
            "dataset": parts[1],
            "continent": parts[2],
            "mode": "click",
            "category": parts[3],
            "n": int(parts[4]) if parts[4].isdigit() else 0,
        }
    elif len(parts) >= 4:
        return {
            "game_type": gt,
            "dataset": parts[1],
            "continent": parts[2],
            "mode": "",
            "category": "",
            "n": int(parts[3]) if parts[3].isdigit() else 0,
        }
    return {"game_type": gt, "dataset": "", "continent": "", "mode": "", "category": "", "n": 0}


def build_config_key(test_key: str) -> str:
    """Build a config key from a test_key by stripping the question count.

    Config keys are used to group rankings across different question counts.
    Returns e.g. 'map-challenge:countries:all:click:all'
    or 'flags:countries:all' for standard games.
    """
    p = parse_test_key(test_key)
    gt = p["game_type"]
    if gt in ("map-challenge", "relief-challenge"):
        return f"{gt}:{p['dataset']}:{p['continent']}:{p['mode']}:{p['category']}"
    return f"{gt}:{p['dataset']}:{p['continent']}"


# Ranking-eligible config filter: exclude custom relief categories and city country-filtered
def is_rankable_config(config_key: str) -> bool:
    """Check if a config key represents a ranking-eligible configuration."""
    parts = config_key.split(":")
    gt = parts[0]
    if gt == "relief-challenge" and len(parts) >= 5:
        category = parts[4]
        # Exclude custom multi-type categories (contain commas)
        if "," in category:
            return False
    return True


def get_week_key(dt: Optional[datetime] = None) -> str:
    """Return ISO week key like '2026-W14'."""
    dt = dt or datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def get_day_key(dt: Optional[datetime] = None) -> str:
    """Return day key like '2026-04-02'."""
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")


# ── Core formulas ────────────────────────────────────────────────────────────

def compute_quality(
    game_type: str,
    score: int,
    total: int,
    per_question_scores: list[float] | None = None,
    avg_score: float | None = None,
) -> float:
    """Compute normalized quality q in [0, 1].

    For scored games (ordering/geostats):
      - Uses per_question_scores if provided: q = sum(scores) / (10 * n)
      - Falls back to avg_score from config: q = avg_score / 10
      - Last resort: q = score / total
    For binary games: q = correct / total
    """
    if game_type in SCORED_GAMES:
        if per_question_scores:
            total_points = sum(per_question_scores)
            max_points = 10 * len(per_question_scores)
            return total_points / max_points if max_points > 0 else 0.0
        if avg_score is not None:
            return min(1.0, max(0.0, avg_score / 10.0))
    return score / total if total > 0 else 0.0


def compute_attempt_score(q: float, n: int, time_seconds: float, tref: float) -> float:
    """S = 1000 * Q * T * C(n)

    Q = q^3            — quality component (precision dominates)
    T = 1/(1+0.35*tpp/tref)  — time component (speed is secondary)
    C = 1 - exp(-n/15) — confidence by length (short runs count less)
    """
    if n <= 0 or tref <= 0:
        return 0.0
    Q = q ** 3
    tpp = time_seconds / n
    T = 1.0 / (1.0 + 0.35 * (tpp / tref))
    C = 1.0 - math.exp(-n / 15.0)
    return 1000.0 * Q * T * C


def compute_percentile(score_s: float, all_scores: list[float]) -> float:
    """Compute percentile of score_s within all_scores (0..100)."""
    if not all_scores:
        return 50.0
    count_below = sum(1 for s in all_scores if s < score_s)
    count_equal = sum(1 for s in all_scores if abs(s - score_s) < 0.001)
    return (count_below + 0.5 * count_equal) / len(all_scores) * 100.0


def update_rating(old_rating: float, percentile: float, lam: float = LAMBDA_RATING) -> float:
    """R_new = (1 - λ) * R_old + λ * P"""
    return (1.0 - lam) * old_rating + lam * percentile


def get_tref(game_type: str, config: dict) -> float:
    """Get reference time per question from game configuration."""
    if game_type == "map-challenge":
        mode = config.get("game_mode", config.get("mode", "click"))
        if mode == "type":
            return config.get("secs_per_item_type", 4)
        return config.get("secs_per_item_click", 6)
    if game_type == "relief-challenge":
        mode = config.get("game_mode", config.get("mode", "click"))
        if mode == "type":
            return config.get("secs_per_item_type", 4)
        return config.get("secs_per_item_click", 8)
    return config.get("secs_per_item", DEFAULT_TREF.get(game_type, 20))


# ── Attempt processing ──────────────────────────────────────────────────────

def process_ranked_attempt(
    user_id: str,
    game_type: str,
    score: int,
    total: int,
    num_questions: int,
    time_ms: int,
    config: dict,
    per_question_scores: list[float] | None = None,
    username: str = "",
) -> dict:
    """Process a ranked (timed) attempt end-to-end.

    1. Compute normalized quality q
    2. Compute attempt score S
    3. Store attempt in ranked_attempts
    4. Compute percentile P within the test
    5. Update test rating R_test (best daily only)
    6. Check/update records (map/relief games)

    Returns dict with attempt details and records broken.
    """
    now = datetime.now(timezone.utc)
    n = num_questions or total
    time_seconds = time_ms / 1000.0

    # 1. Quality
    avg_score = config.get("avg_score")
    if avg_score is not None:
        try:
            avg_score = float(avg_score)
        except (ValueError, TypeError):
            avg_score = None
    q = compute_quality(game_type, score, total, per_question_scores, avg_score)

    # 2. Reference time & attempt score
    tref = get_tref(game_type, config)
    score_s = compute_attempt_score(q, n, time_seconds, tref)
    tpp = time_seconds / n if n > 0 else 0.0

    # 3. Keys
    test_key = build_test_key(game_type, config, n)
    attempt_id = str(uuid.uuid4())
    week_key = get_week_key(now)
    day_key = get_day_key(now)
    created_at = now.isoformat()

    # 4. Store attempt
    attempt_item = {
        "test_key": test_key,
        "attempt_id": attempt_id,
        "user_id": user_id,
        "game_type": game_type,
        "q": Decimal(str(round(q, 6))),
        "score_s": Decimal(str(round(score_s, 4))),
        "n": n,
        "time_seconds": Decimal(str(round(time_seconds, 2))),
        "tpp": Decimal(str(round(tpp, 4))),
        "tref": Decimal(str(round(tref, 2))),
        "week_key": week_key,
        "day_key": day_key,
        "created_at": created_at,
    }
    _attempts_table().put_item(Item=attempt_item)

    # 5. Percentile
    all_scores = _get_test_scores(test_key)
    percentile = compute_percentile(score_s, all_scores)

    # 6. Update test rating
    rating_result = _update_test_rating(
        user_id, test_key, game_type, percentile, day_key
    )

    # 7. Records (map-challenge / relief-challenge)
    records_broken = {}
    if game_type in RECORD_GAMES:
        records_broken = _check_records(
            test_key, user_id, username, q, score_s, tpp, n, time_seconds, created_at
        )

    return {
        "attempt_id": attempt_id,
        "test_key": test_key,
        "q": round(q, 6),
        "score_s": round(score_s, 4),
        "tpp": round(tpp, 4),
        "percentile": round(percentile, 2),
        "rating": rating_result.get("rating", 0),
        "rating_delta": rating_result.get("delta", 0),
        "records_broken": records_broken,
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _get_test_scores(test_key: str) -> list[float]:
    """Query all scores for a test (for percentile computation)."""
    from boto3.dynamodb.conditions import Key

    items: list[dict] = []
    resp = _attempts_table().query(
        KeyConditionExpression=Key("test_key").eq(test_key),
        ProjectionExpression="score_s",
    )
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = _attempts_table().query(
            KeyConditionExpression=Key("test_key").eq(test_key),
            ProjectionExpression="score_s",
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items", []))
    return [float(item["score_s"]) for item in items]


def _update_test_rating(
    user_id: str,
    test_key: str,
    game_type: str,
    percentile: float,
    day_key: str,
) -> dict:
    """Update R_test using EMA.

    - Best daily attempt uses full λ=0.20.
    - Extra daily attempts use reduced λ=0.05.
    """
    resp = _ratings_table().get_item(
        Key={"user_id": user_id, "test_key": test_key}
    )
    existing = resp.get("Item")
    old_rating = float(existing["rating"]) if existing else 50.0
    last_date = existing.get("last_rating_date", "") if existing else ""
    attempts_count = int(existing.get("attempts_count", 0)) if existing else 0
    best_daily_p = float(existing.get("best_daily_percentile", 0)) if existing else 0

    if last_date == day_key:
        if percentile <= best_daily_p:
            lam = LAMBDA_SPAM
        else:
            lam = LAMBDA_RATING
    else:
        best_daily_p = 0
        lam = LAMBDA_RATING

    new_rating = update_rating(old_rating, percentile, lam)
    delta = new_rating - old_rating
    new_best_daily = max(percentile, best_daily_p)
    now = datetime.now(timezone.utc).isoformat()

    _ratings_table().put_item(Item={
        "user_id": user_id,
        "test_key": test_key,
        "game_type": game_type,
        "rating": Decimal(str(round(new_rating, 4))),
        "attempts_count": attempts_count + 1,
        "last_rating_date": day_key,
        "best_daily_percentile": Decimal(str(round(new_best_daily, 2))),
        "updated_at": now,
    })
    return {"rating": round(new_rating, 4), "delta": round(delta, 4)}


# ── Records ──────────────────────────────────────────────────────────────────

def _check_records(
    config_key: str,
    user_id: str,
    username: str,
    q: float,
    score_s: float,
    tpp: float,
    n: int,
    time_seconds: float,
    created_at: str,
) -> dict:
    """Check and update personal records for a configuration.

    Record types:
      quality — ordered by q desc, then S desc, then tpp asc, then n desc
      score   — ordered by S desc
      perfect — only q==1.0, ordered by tpp asc, then n desc
    """
    broken: dict[str, bool] = {}
    record_types = ["quality", "score", "perfect"]

    for rtype in record_types:
        sk = f"{rtype}#{user_id}"
        resp = _records_table().get_item(
            Key={"config_key": config_key, "record_sort": sk}
        )
        existing = resp.get("Item")
        should_update = False

        if rtype == "quality":
            if not existing:
                should_update = True
            else:
                eq = float(existing.get("q", 0))
                es = float(existing.get("score_s", 0))
                et = float(existing.get("tpp", 999999))
                en = int(existing.get("n", 0))
                if (q > eq
                    or (q == eq and score_s > es)
                    or (q == eq and score_s == es and tpp < et)
                    or (q == eq and score_s == es and tpp == et and n > en)):
                    should_update = True

        elif rtype == "score":
            if not existing or score_s > float(existing.get("score_s", 0)):
                should_update = True

        elif rtype == "perfect":
            if q < 1.0:
                continue
            if not existing:
                should_update = True
            else:
                et = float(existing.get("tpp", 999999))
                en = int(existing.get("n", 0))
                if tpp < et or (tpp == et and n > en):
                    should_update = True

        if should_update:
            _records_table().put_item(Item={
                "config_key": config_key,
                "record_sort": sk,
                "record_type": rtype,
                "user_id": user_id,
                "username": username,
                "q": Decimal(str(round(q, 6))),
                "score_s": Decimal(str(round(score_s, 4))),
                "tpp": Decimal(str(round(tpp, 4))),
                "n": n,
                "time_seconds": Decimal(str(round(time_seconds, 2))),
                "created_at": created_at,
            })
            broken[rtype] = True

    return broken


def get_records(config_key: str) -> dict:
    """Get all records for a configuration, grouped by record_type."""
    from boto3.dynamodb.conditions import Key

    resp = _records_table().query(
        KeyConditionExpression=Key("config_key").eq(config_key),
    )
    items = resp.get("Items", [])
    records: dict[str, list] = {}
    for item in items:
        rtype = item.get("record_type", "")
        if rtype not in records:
            records[rtype] = []
        records[rtype].append({
            "user_id": item["user_id"],
            "username": item.get("username", "???"),
            "q": float(item.get("q", 0)),
            "score_s": float(item.get("score_s", 0)),
            "tpp": float(item.get("tpp", 0)),
            "n": int(item.get("n", 0)),
            "time_seconds": float(item.get("time_seconds", 0)),
            "created_at": item.get("created_at", ""),
        })
    for rtype in records:
        if rtype == "quality":
            records[rtype].sort(key=lambda r: (-r["q"], -r["score_s"], r["tpp"]))
        elif rtype == "score":
            records[rtype].sort(key=lambda r: -r["score_s"])
        elif rtype == "perfect":
            records[rtype].sort(key=lambda r: (r["tpp"], -r["n"]))
    return records


# ── User queries ─────────────────────────────────────────────────────────────

def get_user_attempts(user_id: str, limit: int = 50) -> list[dict]:
    """Get recent ranked attempts for a user (newest first)."""
    from boto3.dynamodb.conditions import Key

    resp = _attempts_table().query(
        IndexName="user-time-index",
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [{
        "attempt_id": item["attempt_id"],
        "test_key": item["test_key"],
        "game_type": item.get("game_type", ""),
        "q": float(item.get("q", 0)),
        "score_s": float(item.get("score_s", 0)),
        "n": int(item.get("n", 0)),
        "tpp": float(item.get("tpp", 0)),
        "week_key": item.get("week_key", ""),
        "day_key": item.get("day_key", ""),
        "created_at": item.get("created_at", ""),
    } for item in resp.get("Items", [])]


def get_user_test_ratings(user_id: str) -> list[dict]:
    """Get all test ratings for a user."""
    from boto3.dynamodb.conditions import Key

    resp = _ratings_table().query(
        KeyConditionExpression=Key("user_id").eq(user_id),
    )
    return [{
        "test_key": item["test_key"],
        "game_type": item.get("game_type", ""),
        "rating": float(item.get("rating", 0)),
        "attempts_count": int(item.get("attempts_count", 0)),
        "updated_at": item.get("updated_at", ""),
    } for item in resp.get("Items", [])]
