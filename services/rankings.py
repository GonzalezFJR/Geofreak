"""Rankings service — game, season, and weekly ranking computation.

Computes and materializes rankings into leaderboards_cache:
  - Per-game rankings (RG)   — best 5 test ratings, weighted sum
  - Season rankings (RT)     — last 12 weeks, best 4 game rankings
  - Weekly rankings (RS)     — current/specific week, best 3 game ratings
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from core.aws import get_dynamodb_resource
from core.config import get_settings
from services.scoring import (
    ALL_GAME_TYPES,
    compute_percentile,
    get_week_key,
)


# ── DynamoDB table accessors ─────────────────────────────────────────────────

def _ratings_table():
    return get_dynamodb_resource().Table(get_settings().table_name("test_ratings"))


def _attempts_table():
    return get_dynamodb_resource().Table(get_settings().table_name("ranked_attempts"))


def _lb_table():
    return get_dynamodb_resource().Table(get_settings().table_name("leaderboards_cache"))


def _users_table():
    return get_dynamodb_resource().Table(get_settings().table_name("users"))


# ── Core ranking formulas ────────────────────────────────────────────────────

def compute_game_ranking(test_ratings: list[float]) -> float:
    """RG = R1 + 0.85*R2 + 0.70*R3 + 0.55*R4 + 0.40*R5"""
    weights = [1.0, 0.85, 0.70, 0.55, 0.40]
    sorted_ratings = sorted(test_ratings, reverse=True)
    return sum(r * w for r, w in zip(sorted_ratings[:5], weights))


def compute_game_ranking_final(rg: float, tests_valid: int) -> float:
    """RG_final = RG * (1 + 0.02 * min(10, tests_valid - 1))"""
    b = 1 + 0.02 * min(10, max(0, tests_valid - 1))
    return rg * b


def compute_season_ranking(game_rankings: list[float]) -> float:
    """RT = G1 + 0.80*G2 + 0.60*G3 + 0.45*G4"""
    weights = [1.0, 0.80, 0.60, 0.45]
    sorted_rankings = sorted(game_rankings, reverse=True)
    return sum(r * w for r, w in zip(sorted_rankings[:4], weights))


def compute_season_final(
    rt: float, num_active_games: int, num_active_weeks: int
) -> float:
    """RT_final = RT * B_variedad * B_constancia"""
    b_variety = 1 + 0.04 * min(6, max(0, num_active_games - 1))
    b_constancy = 1 + 0.02 * min(8, max(0, num_active_weeks - 1))
    return rt * b_variety * b_constancy


def compute_weekly_game_rating(test_percentiles: list[float]) -> float:
    """RWG = W1 + 0.75*W2 + 0.50*W3 + 0.30*W4"""
    weights = [1.0, 0.75, 0.50, 0.30]
    sorted_p = sorted(test_percentiles, reverse=True)
    return sum(p * w for p, w in zip(sorted_p[:4], weights))


def compute_weekly_base(game_ratings: list[float]) -> float:
    """RS_base = H1 + 0.80*H2 + 0.60*H3"""
    weights = [1.0, 0.80, 0.60]
    sorted_r = sorted(game_ratings, reverse=True)
    return sum(r * w for r, w in zip(sorted_r[:3], weights))


def compute_weekly_final(
    rs_base: float, num_games: int, num_tests: int, num_days: int
) -> float:
    """RS_final = RS_base * Bv_sem * Ba_sem * Br_sem"""
    bv = 1 + 0.05 * min(4, max(0, num_games - 1))
    ba = 1 + 0.015 * min(20, max(0, num_tests - 1))
    br = 1 + 0.02 * min(5, max(0, num_days - 1))
    return rs_base * bv * ba * br


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


# ── Full-scan helpers ────────────────────────────────────────────────────────

def _scan_all_ratings() -> list[dict]:
    table = _ratings_table()
    items: list[dict] = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def _scan_all_attempts() -> list[dict]:
    table = _attempts_table()
    items: list[dict] = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


TOP_N = 50


# ── Game rankings ────────────────────────────────────────────────────────────

def rebuild_game_rankings() -> int:
    """Rebuild materialized per-game rankings from test_ratings."""
    all_ratings = _scan_all_ratings()
    if not all_ratings:
        return 0

    # user_id → game_type → [ratings]
    user_game_ratings: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item in all_ratings:
        uid = item["user_id"]
        gt = item.get("game_type", "")
        rating = float(item.get("rating", 0))
        user_game_ratings[uid][gt].append(rating)

    user_ids = list(user_game_ratings.keys())
    usernames = _load_usernames(user_ids)

    count = 0
    now = datetime.now(timezone.utc).isoformat()

    for game_type in ALL_GAME_TYPES:
        entries: list[dict] = []
        for uid, games in user_game_ratings.items():
            if game_type not in games:
                continue
            ratings = games[game_type]
            rg = compute_game_ranking(ratings)
            rg_final = compute_game_ranking_final(rg, len(ratings))
            entries.append({
                "user_id": uid,
                "username": usernames.get(uid, "???"),
                "value": Decimal(str(round(rg_final, 4))),
                "rg": Decimal(str(round(rg, 4))),
                "tests_valid": len(ratings),
            })

        entries.sort(key=lambda e: float(e["value"]), reverse=True)
        for i, e in enumerate(entries[:TOP_N], 1):
            e["rank"] = i

        lid = f"game#{game_type}#ranking"
        _lb_table().put_item(Item={
            "leaderboard_id": lid,
            "scope": "game",
            "game_type": game_type,
            "metric": "ranking",
            "entries": entries[:TOP_N],
            "updated_at": now,
        })
        count += 1

    return count


def get_user_game_ranking(user_id: str, game_type: str) -> dict:
    """Compute a single user's game ranking on-the-fly."""
    from boto3.dynamodb.conditions import Key

    resp = _ratings_table().query(
        KeyConditionExpression=Key("user_id").eq(user_id),
    )
    ratings = [
        float(item["rating"])
        for item in resp.get("Items", [])
        if item.get("game_type") == game_type
    ]
    if not ratings:
        return {"rg": 0, "rg_final": 0, "tests_valid": 0}

    rg = compute_game_ranking(ratings)
    rg_final = compute_game_ranking_final(rg, len(ratings))
    return {
        "rg": round(rg, 4),
        "rg_final": round(rg_final, 4),
        "tests_valid": len(ratings),
    }


# ── Season rankings (12-week window) ────────────────────────────────────────

def rebuild_season_rankings() -> int:
    """Rebuild season rankings using attempts from the last 12 weeks."""
    now = datetime.now(timezone.utc)
    season_weeks = {get_week_key(now - timedelta(weeks=w)) for w in range(12)}

    all_attempts = _scan_all_attempts()
    season_attempts = [
        a for a in all_attempts if a.get("week_key") in season_weeks
    ]
    if not season_attempts:
        return 0

    # All-time scores by test (for percentile computation)
    test_scores: dict[str, list[float]] = defaultdict(list)
    for a in all_attempts:
        test_scores[a.get("test_key", "")].append(float(a.get("score_s", 0)))

    # Per-user: best attempt per test in season, active weeks/games
    user_test_best: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"score_s": 0, "game_type": ""})
    )
    user_weeks: dict[str, set[str]] = defaultdict(set)
    user_games: dict[str, set[str]] = defaultdict(set)

    for a in season_attempts:
        uid = a.get("user_id", "")
        tk = a.get("test_key", "")
        gt = a.get("game_type", "")
        ss = float(a.get("score_s", 0))
        wk = a.get("week_key", "")

        if ss > user_test_best[uid][tk]["score_s"]:
            user_test_best[uid][tk] = {"score_s": ss, "game_type": gt}
        user_weeks[uid].add(wk)
        user_games[uid].add(gt)

    user_ids = list(user_test_best.keys())
    usernames = _load_usernames(user_ids)

    entries: list[dict] = []
    for uid in user_ids:
        n_weeks = len(user_weeks[uid])
        n_games = len(user_games[uid])
        total_attempts = sum(
            1 for a in season_attempts if a.get("user_id") == uid
        )
        eligible = (n_weeks >= 3 and n_games >= 2) or total_attempts >= 10
        if not eligible:
            continue

        # Test scores → percentiles → game rankings
        game_test_percentiles: dict[str, list[float]] = defaultdict(list)
        for tk, info in user_test_best[uid].items():
            p = compute_percentile(info["score_s"], test_scores.get(tk, []))
            game_test_percentiles[info["game_type"]].append(p)

        game_rankings: list[float] = []
        for gt, percentiles in game_test_percentiles.items():
            rg = compute_game_ranking(percentiles)
            rg_final = compute_game_ranking_final(rg, len(percentiles))
            game_rankings.append(rg_final)

        if not game_rankings:
            continue

        rt = compute_season_ranking(game_rankings)
        rt_final = compute_season_final(rt, n_games, n_weeks)

        entries.append({
            "user_id": uid,
            "username": usernames.get(uid, "???"),
            "value": Decimal(str(round(rt_final, 4))),
            "rt": Decimal(str(round(rt, 4))),
            "num_games": n_games,
            "num_weeks": n_weeks,
        })

    entries.sort(key=lambda e: float(e["value"]), reverse=True)
    for i, e in enumerate(entries[:TOP_N], 1):
        e["rank"] = i

    now_str = datetime.now(timezone.utc).isoformat()
    _lb_table().put_item(Item={
        "leaderboard_id": "season#all#ranking",
        "scope": "season",
        "game_type": "all",
        "metric": "ranking",
        "entries": entries[:TOP_N],
        "updated_at": now_str,
    })
    return 1


# ── Weekly rankings ──────────────────────────────────────────────────────────

def rebuild_weekly_rankings(week_key: Optional[str] = None) -> int:
    """Rebuild weekly ranking for a specific week (defaults to current)."""
    if not week_key:
        week_key = get_week_key()

    all_attempts = _scan_all_attempts()
    week_attempts = [a for a in all_attempts if a.get("week_key") == week_key]
    if not week_attempts:
        return 0

    # All-time test scores for percentiles
    test_scores: dict[str, list[float]] = defaultdict(list)
    for a in all_attempts:
        test_scores[a.get("test_key", "")].append(float(a.get("score_s", 0)))

    # Group by user
    user_data: dict[str, dict] = defaultdict(lambda: {
        "tests": defaultdict(lambda: {"score_s": 0.0, "game_type": ""}),
        "games": set(),
        "days": set(),
    })
    for a in week_attempts:
        uid = a.get("user_id", "")
        tk = a.get("test_key", "")
        gt = a.get("game_type", "")
        ss = float(a.get("score_s", 0))
        dk = a.get("day_key", "")

        if ss > user_data[uid]["tests"][tk]["score_s"]:
            user_data[uid]["tests"][tk] = {"score_s": ss, "game_type": gt}
        user_data[uid]["games"].add(gt)
        user_data[uid]["days"].add(dk)

    user_ids = list(user_data.keys())
    usernames = _load_usernames(user_ids)

    entries: list[dict] = []
    for uid, data in user_data.items():
        n_tests = len(data["tests"])
        n_games = len(data["games"])
        n_days = len(data["days"])

        # Eligibility: min 3 tests, min 2 days, and (2 games or 1 game with ≥2 tests)
        if n_tests < 3 or n_days < 2:
            continue
        game_test_count: dict[str, int] = defaultdict(int)
        for tk, info in data["tests"].items():
            game_test_count[info["game_type"]] += 1
        if n_games < 2 and not any(c >= 2 for c in game_test_count.values()):
            continue

        # Compute weekly game ratings
        game_test_percentiles: dict[str, list[float]] = defaultdict(list)
        for tk, info in data["tests"].items():
            p = compute_percentile(info["score_s"], test_scores.get(tk, []))
            game_test_percentiles[info["game_type"]].append(p)

        game_ratings: list[float] = []
        for gt, percentiles in game_test_percentiles.items():
            rwg = compute_weekly_game_rating(percentiles)
            game_ratings.append(rwg)

        if not game_ratings:
            continue

        rs_base = compute_weekly_base(game_ratings)
        rs_final = compute_weekly_final(rs_base, n_games, n_tests, n_days)

        entries.append({
            "user_id": uid,
            "username": usernames.get(uid, "???"),
            "value": Decimal(str(round(rs_final, 4))),
            "rs_base": Decimal(str(round(rs_base, 4))),
            "num_games": n_games,
            "num_tests": n_tests,
            "num_days": n_days,
        })

    entries.sort(key=lambda e: float(e["value"]), reverse=True)
    for i, e in enumerate(entries[:TOP_N], 1):
        e["rank"] = i

    now_str = datetime.now(timezone.utc).isoformat()
    _lb_table().put_item(Item={
        "leaderboard_id": f"weekly#{week_key}#ranking",
        "scope": "weekly",
        "game_type": "all",
        "metric": "ranking",
        "entries": entries[:TOP_N],
        "updated_at": now_str,
        "week_key": week_key,
    })
    return 1


# ── Rebuild all ──────────────────────────────────────────────────────────────

def rebuild_all_rankings() -> dict:
    """Rebuild all ranking types. Returns counts."""
    game_count = rebuild_game_rankings()
    season_count = rebuild_season_rankings()
    weekly_count = rebuild_weekly_rankings()
    return {
        "game_rankings": game_count,
        "season_rankings": season_count,
        "weekly_rankings": weekly_count,
    }


# ── Public getters ───────────────────────────────────────────────────────────

def get_game_ranking(game_type: str) -> Optional[dict]:
    lid = f"game#{game_type}#ranking"
    resp = _lb_table().get_item(Key={"leaderboard_id": lid})
    return resp.get("Item")


def get_season_ranking() -> Optional[dict]:
    resp = _lb_table().get_item(Key={"leaderboard_id": "season#all#ranking"})
    return resp.get("Item")


def get_weekly_ranking(week_key: Optional[str] = None) -> Optional[dict]:
    if not week_key:
        week_key = get_week_key()
    lid = f"weekly#{week_key}#ranking"
    resp = _lb_table().get_item(Key={"leaderboard_id": lid})
    return resp.get("Item")


def get_user_ranking_position(
    user_id: str,
    scope: str = "game",
    game_type: str = "comparison",
) -> Optional[int]:
    """Return the user's 1-based position in a cached ranking, or None."""
    if scope == "game":
        lb = get_game_ranking(game_type)
    elif scope == "season":
        lb = get_season_ranking()
    elif scope == "weekly":
        lb = get_weekly_ranking()
    else:
        return None

    if not lb:
        return None

    for entry in lb.get("entries", []):
        if entry.get("user_id") == user_id:
            return int(entry.get("rank", 0))
    return None
