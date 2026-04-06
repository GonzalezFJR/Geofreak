"""Fake daily challenge players — 30 bot users that play every day.

On the first ranking request of each day, this module ensures all 30 fake
users have a daily_scores entry for today with a random score_s in [90, 330].
Subsequent calls the same day are no-ops.
"""

import logging
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.aws import get_dynamodb_resource
from core.config import get_settings

log = logging.getLogger(__name__)

FAKE_USERNAMES = [
    "victor_perez", "javier_fernandez", "Gabarus", "Pascu", "Natasha_geo",
    "LawrenceM", "rober_wehin", "wolf", "animagly", "Draco",
    "Umb0r", "paula_marin", "Ghst1", "Pxlt", "Ldino",
    "sarasar", "Naraná", "JaviYo", "MaríaG", "Stef",
    "Lindsey", "Thor", "Einstein", "will_brucker", "josh_shannon",
    "german", "Freya.A", "dani_garcia", "ElGuti", "Mytiku",
]

# Cache: set once per process lifetime; reset on restart
_seeded_today: str | None = None
_backfilled: bool = False


def _users_table():
    return get_dynamodb_resource().Table(get_settings().table_name("users"))


def _daily_scores_table():
    return get_dynamodb_resource().Table(get_settings().table_name("daily_scores"))


# ── Ensure fake users exist ──────────────────────────────────────────────────

def _ensure_fake_users() -> dict[str, str]:
    """Create fake users if they don't exist. Returns {username: user_id}."""
    from boto3.dynamodb.conditions import Key

    table = _users_table()
    mapping: dict[str, str] = {}

    for uname in FAKE_USERNAMES:
        resp = table.query(
            IndexName="username-index",
            KeyConditionExpression=Key("username").eq(uname),
            Limit=1,
        )
        items = resp.get("Items", [])
        if items:
            mapping[uname] = items[0]["user_id"]
        else:
            uid = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            table.put_item(Item={
                "user_id": uid,
                "username": uname,
                "email": f"{uid}@fake.geofreak.local",
                "password_hash": "",
                "created_at": now,
                "updated_at": now,
                "plan": "free",
                "role": "free",
                "status": "active",
                "country": "",
                "language": "es",
                "settings": {},
                "is_fake": True,
            })
            mapping[uname] = uid
            log.info("Created fake user %s (%s)", uname, uid)

    return mapping


# ── Generate today's scores ─────────────────────────────────────────────────

def _already_played_today(user_id: str, today: str) -> bool:
    """Check if a fake user already has a score for today."""
    from boto3.dynamodb.conditions import Key

    resp = _daily_scores_table().query(
        KeyConditionExpression=Key("user_id").eq(user_id) & Key("date").eq(today),
        Limit=1,
    )
    return len(resp.get("Items", [])) > 0


def _generate_fake_score(user_id: str, username: str, today: str) -> None:
    """Insert a random daily score for a fake user."""
    score_s = random.uniform(90, 330)

    # Reverse-engineer plausible raw values from score_s
    # S = 1000 * Q * T * C  where Q=q^3, T=1/(1+0.5*tpp/tref), C=1-e^(-n/15)
    n = 20
    tref = 20.0
    C = 1.0 - math.exp(-n / 15.0)  # ~0.7364
    # S = 1000 * q^3 * T * C  =>  q^3 * T = S / (1000 * C)
    target = score_s / (1000.0 * C)
    # Pick a plausible q and derive tpp
    q = random.uniform(0.35, 0.85)
    Q = q ** 3
    if Q > 0:
        T = min(1.0, target / Q)
    else:
        T = 0.5
    # T = 1/(1+0.5*tpp/tref) => tpp = tref * 2 * (1/T - 1)
    if T > 0.01:
        tpp = tref * 2.0 * (1.0 / T - 1.0)
    else:
        tpp = tref * 4.0
    tpp = max(tref * 0.3, tpp)

    time_seconds = tpp * n
    score = max(1, int(q * n))

    now = datetime.now(timezone.utc).isoformat()
    _daily_scores_table().put_item(Item={
        "user_id": user_id,
        "date": today,
        "username": username,
        "game_type": "comparison",
        "score": score,
        "total": n,
        "time_ms": int(time_seconds * 1000),
        "num_questions": n,
        "q": Decimal(str(round(q, 6))),
        "score_s": Decimal(str(round(score_s, 4))),
        "tpp": Decimal(str(round(tpp, 4))),
        "tref": Decimal(str(round(tref, 2))),
        "created_at": now,
    })


# ── Public entry point ───────────────────────────────────────────────────────

def ensure_fake_daily_scores() -> None:
    """Ensure all 30 fake users have played today's daily challenge.

    Safe to call multiple times per day — only generates scores once.
    On first run ever, backfills previous days of the current month
    so fake users meet the 3-day minimum for monthly rankings.
    After generating new scores, forces a ranking rebuild.
    """
    global _seeded_today, _backfilled
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Fast path: already seeded this process today
    if _seeded_today == today:
        return

    user_map = _ensure_fake_users()
    generated = False

    # Backfill previous days of the month (only once per process)
    if not _backfilled:
        generated = _backfill_month(user_map, today)
        _backfilled = True

    # Generate today's scores
    first_uid = next(iter(user_map.values()))
    if not _already_played_today(first_uid, today):
        log.info("Generating fake daily scores for %s (%d users)", today, len(user_map))
        for username, uid in user_map.items():
            _generate_fake_score(uid, username, today)
        generated = True

    # Force rebuild rankings if we inserted any new scores
    if generated:
        from services.daily_rankings import rebuild_all_daily_rankings
        rebuild_all_daily_rankings()
        log.info("Daily rankings rebuilt after fake score generation")

    _seeded_today = today


def _backfill_month(user_map: dict[str, str], today_str: str) -> bool:
    """Backfill daily scores for all previous days of the current month.

    Skips days where the first fake user already has a score.
    Returns True if any new scores were generated.
    """
    from boto3.dynamodb.conditions import Key

    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    first_day = today.replace(day=1)
    first_uid = next(iter(user_map.values()))
    generated = False

    day = first_day
    while day < today:
        date_str = day.strftime("%Y-%m-%d")
        # Check if already backfilled for this day
        resp = _daily_scores_table().query(
            KeyConditionExpression=Key("user_id").eq(first_uid) & Key("date").eq(date_str),
            Limit=1,
        )
        if not resp.get("Items"):
            log.info("Backfilling fake daily scores for %s", date_str)
            for username, uid in user_map.items():
                _generate_fake_score(uid, username, date_str)
            generated = True
        day += timedelta(days=1)

    return generated
