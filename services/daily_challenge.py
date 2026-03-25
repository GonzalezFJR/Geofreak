"""Daily challenge service — serves pre-generated daily challenges.

Challenges are stored in S3 at daily_challenges/YYYY-MM-DD.json.
A local cache file avoids repeated S3 downloads within the same day.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.aws import get_dynamodb_resource, get_s3_client
from core.config import get_settings

log = logging.getLogger(__name__)

S3_PREFIX = "daily_challenges"
_BACKFILL_DAYS = 90

_LOCAL_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "static", "data", "daily_challenges"
)
_LOCAL_CACHE_FILE = os.path.join(_LOCAL_CACHE_DIR, "current.json")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_local_cache() -> Optional[dict]:
    """Read local cache if it exists and matches today's date."""
    if not os.path.isfile(_LOCAL_CACHE_FILE):
        return None
    try:
        with open(_LOCAL_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") == _today_utc():
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_local_cache(data: dict) -> None:
    """Save challenge data to local cache."""
    os.makedirs(_LOCAL_CACHE_DIR, exist_ok=True)
    with open(_LOCAL_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _download_from_s3(date_str: str) -> Optional[dict]:
    """Download a challenge JSON from S3 for the given date."""
    settings = get_settings()
    s3 = get_s3_client()
    key = f"{S3_PREFIX}/{date_str}.json"
    try:
        resp = s3.get_object(Bucket=settings.s3_bucket_name, Key=key)
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)
    except Exception:
        return None


def _generate_today() -> None:
    """Run the generation script for today only (1 day), blocking."""
    today = _today_utc()
    log.info("No daily challenge found for %s — generating today's …", today)
    try:
        subprocess.run(
            [sys.executable, "-m", "scripts.generate_daily_challenges",
             "--start", today, "--days", "1"],
            check=True,
            timeout=30,
        )
    except Exception as exc:
        log.error("Daily challenge generation failed: %s", exc)


def _generate_next_days_background() -> None:
    """Kick off generation of the next N days in background (fire-and-forget)."""
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    log.info("Launching background generation of %d days starting %s", _BACKFILL_DAYS, tomorrow)
    try:
        subprocess.Popen(
            [sys.executable, "-m", "scripts.generate_daily_challenges",
             "--start", tomorrow, "--days", str(_BACKFILL_DAYS)],
        )
    except Exception as exc:
        log.error("Background daily challenge generation failed to start: %s", exc)


def get_daily_challenge() -> Optional[dict]:
    """Return today's daily challenge.

    1. Check local cache — if valid for today, return it.
    2. Otherwise download from S3, cache locally, and return.
    3. If S3 has no challenge for today, generate it on the fly, then retry S3.
    """
    cached = _read_local_cache()
    if cached is not None:
        return cached

    today = _today_utc()
    data = _download_from_s3(today)
    if data is not None:
        _save_local_cache(data)
        return data

    # Fallback: generate today's challenge and retry
    _generate_today()
    data = _download_from_s3(today)
    if data is not None:
        _save_local_cache(data)
        # Also backfill next 90 days in background
        _generate_next_days_background()
        return data

    return None


# ── User daily result tracking (stored in user_stats) ─────────────────────

def _user_stats_table():
    return get_dynamodb_resource().Table(get_settings().table_name("user_stats"))


def get_user_daily_result(user_id: str) -> Optional[dict]:
    """If the user already completed today's challenge, return their result."""
    from services.user_stats import get_user_stats
    stats = get_user_stats(user_id)
    if not stats:
        return None
    if stats.get("last_daily_date") == _today_utc():
        return stats.get("last_daily_result")
    return None


def save_user_daily_result(user_id: str, result: dict) -> None:
    """Save today's daily challenge result to the user's stats."""
    _user_stats_table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET last_daily_date = :d, last_daily_result = :r",
        ExpressionAttributeValues={
            ":d": _today_utc(),
            ":r": result,
        },
    )
