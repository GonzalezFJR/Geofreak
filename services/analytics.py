"""Analytics service — DynamoDB counters + S3 event archival.

Counters are stored in DynamoDB with atomic ADD operations so they
persist across container restarts without any flush logic.

Events are buffered in memory and flushed to S3 as JSONL files for
historical archival and the admin dashboard.

DynamoDB table schema (geofreak_analytics):
    pk (HASH, S) : "all" for lifetime counters, "daily:YYYY-MM-DD" for daily
    sk (RANGE, S): event type (e.g. "total", "match_finished",
                   "match_finished#map_challenge")
    value (N)    : counter value (atomically incremented)
    updated_at (S): ISO timestamp of last increment

Usage from any service/router:
    from services.analytics import track
    track("match_finished", {"match_id": "abc", "game_type": "map_challenge", ...})
"""

import json
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any

from boto3.dynamodb.conditions import Key

from core.aws import get_dynamodb_resource, get_s3_client
from core.config import get_settings

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

_S3_PREFIX = "analytics/events"
_RING_BUFFER_MAX = 500

# Fields that generate sub-counters (event_type → data key(s))
_SUB_COUNTER_FIELDS: dict[str, list[str]] = {
    "match_finished": ["game_type", "language"],
    "game_started": ["game"],
    "duel_created": ["game_type"],
    "page_view": ["page"],
}

# ── Internal state ───────────────────────────────────────────────────────────

_buffer: list[dict] = []
_lock = threading.Lock()
_ring: deque[dict] = deque(maxlen=_RING_BUFFER_MAX)


# ── DynamoDB helpers ─────────────────────────────────────────────────────────

def _table():
    return get_dynamodb_resource().Table(get_settings().table_name("analytics"))


def _increment_counters(event_type: str, data: dict, now: datetime) -> None:
    """Atomically increment DynamoDB counters for an event."""
    try:
        table = _table()
        today = now.strftime("%Y-%m-%d")
        ts = now.isoformat()

        # Build list of (pk, sk) pairs to increment
        keys = [
            ("all", "total"),
            ("all", event_type),
            (f"daily:{today}", "total"),
            (f"daily:{today}", event_type),
        ]

        # Add sub-counters if applicable (e.g. match_finished#map_challenge)
        sub_fields = _SUB_COUNTER_FIELDS.get(event_type, [])
        for sub_field in sub_fields:
            if data.get(sub_field):
                sub_sk = f"{event_type}#{data[sub_field]}"
                keys.append(("all", sub_sk))
                keys.append((f"daily:{today}", sub_sk))

        for pk, sk in keys:
            table.update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="ADD #v :inc SET updated_at = :ts",
                ExpressionAttributeNames={"#v": "value"},
                ExpressionAttributeValues={":inc": 1, ":ts": ts},
            )
    except Exception:
        logger.exception("Failed to increment DynamoDB counters")


# ── Public API ───────────────────────────────────────────────────────────────

def track(event_type: str, data: dict[str, Any] | None = None) -> None:
    """Record an analytics event. Non-blocking, thread-safe."""
    now = datetime.now(timezone.utc)
    ev_data = data or {}
    event = {
        "event": event_type,
        "ts": now.isoformat(),
        "data": ev_data,
    }

    with _lock:
        _ring.append(event)
        _buffer.append(event)
        flush_size = get_settings().analytics_flush_size
        if len(_buffer) >= flush_size:
            _flush_locked()

    # Persist counters to DynamoDB in background thread
    threading.Thread(
        target=_increment_counters, args=(event_type, ev_data, now), daemon=True
    ).start()


def flush() -> None:
    """Force-flush the current buffer to S3. Call on shutdown."""
    with _lock:
        _flush_locked()


def get_recent_events(limit: int = 50) -> list[dict]:
    """Return the most recent events from the ring buffer."""
    with _lock:
        items = list(_ring)
    return items[-limit:][::-1]  # newest first


def get_counters() -> dict[str, int]:
    """Return all lifetime counters from DynamoDB."""
    try:
        resp = _table().query(
            KeyConditionExpression=Key("pk").eq("all"),
        )
        items = resp.get("Items", [])
        return {
            item["sk"]: int(item.get("value", 0))
            for item in items
            if item["sk"] != "total"
        }
    except Exception:
        logger.exception("Failed to read DynamoDB counters")
        return {}


def get_counter(event_type: str) -> int:
    try:
        resp = _table().get_item(Key={"pk": "all", "sk": event_type})
        item = resp.get("Item")
        return int(item["value"]) if item else 0
    except Exception:
        return 0


def get_daily_counters(date_str: str | None = None) -> dict[str, int]:
    """Return counters for a specific day (default: today)."""
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        resp = _table().query(
            KeyConditionExpression=Key("pk").eq(f"daily:{date_str}"),
        )
        items = resp.get("Items", [])
        return {
            item["sk"]: int(item.get("value", 0))
            for item in items
        }
    except Exception:
        logger.exception("Failed to read daily counters")
        return {}


def get_total_events() -> int:
    """Return the all-time total event count."""
    try:
        resp = _table().get_item(Key={"pk": "all", "sk": "total"})
        item = resp.get("Item")
        return int(item["value"]) if item else 0
    except Exception:
        return 0


def get_daily_counters_range(days: int = 30) -> list[dict]:
    """Return daily counters for the last N days. Each entry: {date, counters}."""
    now = datetime.now(timezone.utc)
    result = []
    for i in range(days):
        d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        counters = get_daily_counters(d)
        if counters:
            result.append({"date": d, "counters": counters})
    return result


# ── S3 flushing (event archival) ─────────────────────────────────────────────

def _flush_locked() -> None:
    """Flush buffer to S3. Must be called while holding _lock."""
    if not _buffer:
        return

    to_write = list(_buffer)
    _buffer.clear()

    t = threading.Thread(
        target=_write_events_to_s3, args=(to_write,), daemon=True
    )
    t.start()


def _write_events_to_s3(events: list[dict]) -> None:
    """Write a batch of events to S3 as JSONL."""
    try:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        key = (
            f"{_S3_PREFIX}/{now.year:04d}/{now.month:02d}/{now.day:02d}/"
            f"{now.hour:02d}-{uuid.uuid4().hex[:12]}.jsonl"
        )
        body = "\n".join(json.dumps(e, ensure_ascii=False) for e in events)
        get_s3_client().put_object(
            Bucket=settings.s3_bucket_name,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/x-ndjson",
        )
    except Exception:
        logger.exception("Failed to write events to S3")


# ── S3 reading for dashboard ────────────────────────────────────────────────

def count_s3_events_today() -> int:
    """Count approximate number of JSONL files written today."""
    try:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        prefix = f"{_S3_PREFIX}/{now.year:04d}/{now.month:02d}/{now.day:02d}/"
        resp = get_s3_client().list_objects_v2(
            Bucket=settings.s3_bucket_name,
            Prefix=prefix,
        )
        return resp.get("KeyCount", 0)
    except Exception:
        return 0


def list_s3_event_files(days: int = 7, max_keys: int = 100) -> list[dict]:
    """List recent event files in S3 for the admin dashboard."""
    try:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        files: list[dict] = []
        for day_offset in range(days):
            d = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            d = d - timedelta(days=day_offset)
            prefix = f"{_S3_PREFIX}/{d.year:04d}/{d.month:02d}/{d.day:02d}/"
            try:
                resp = get_s3_client().list_objects_v2(
                    Bucket=settings.s3_bucket_name,
                    Prefix=prefix,
                    MaxKeys=max_keys,
                )
                for obj in resp.get("Contents", []):
                    files.append({
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "date": obj["LastModified"].isoformat() if hasattr(obj["LastModified"], "isoformat") else str(obj["LastModified"]),
                    })
            except Exception:
                continue
        return files[:max_keys]
    except Exception:
        return []


def load_recent_events_s3(limit: int = 50) -> list[dict]:
    """Load recent events from S3 JSONL files for the dashboard."""
    try:
        settings = get_settings()
        s3 = get_s3_client()
        now = datetime.now(timezone.utc)
        events: list[dict] = []

        for day_offset in range(3):
            d = now - timedelta(days=day_offset)
            prefix = f"{_S3_PREFIX}/{d.year:04d}/{d.month:02d}/{d.day:02d}/"
            try:
                resp = s3.list_objects_v2(
                    Bucket=settings.s3_bucket_name,
                    Prefix=prefix,
                )
                objects = sorted(
                    resp.get("Contents", []),
                    key=lambda o: o["LastModified"],
                    reverse=True,
                )
                for obj in objects:
                    if len(events) >= limit:
                        break
                    try:
                        file_resp = s3.get_object(
                            Bucket=settings.s3_bucket_name,
                            Key=obj["Key"],
                        )
                        content = file_resp["Body"].read().decode("utf-8")
                        for line in content.strip().split("\n"):
                            if line.strip():
                                events.append(json.loads(line))
                    except Exception:
                        continue
            except Exception:
                continue
            if len(events) >= limit:
                break

        events.sort(key=lambda e: e.get("ts", ""), reverse=True)
        return events[:limit]
    except Exception:
        return []
