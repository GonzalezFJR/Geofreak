"""Daily challenge service — serves pre-generated daily challenges.

Challenges are stored in S3 at daily_challenges/YYYY-MM-DD.json.
A local cache file avoids repeated S3 downloads within the same day.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from core.aws import get_s3_client
from core.config import get_settings

S3_PREFIX = "daily_challenges"

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


def get_daily_challenge() -> Optional[dict]:
    """Return today's daily challenge.

    1. Check local cache — if valid for today, return it.
    2. Otherwise download from S3, cache locally, and return.
    3. If S3 has no challenge for today, return None.
    """
    cached = _read_local_cache()
    if cached is not None:
        return cached

    today = _today_utc()
    data = _download_from_s3(today)
    if data is not None:
        _save_local_cache(data)
        return data

    return None
