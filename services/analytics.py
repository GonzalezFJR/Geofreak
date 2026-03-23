"""Analytics service — buffer events in memory, flush to S3 as JSONL.

Each flush writes one file to:
    s3://{bucket}/analytics/events/{YYYY}/{MM}/{DD}/{HH}-{uuid4}.jsonl

Events are also kept in a small in-memory ring buffer (last ~500) so the
admin dashboard can show recent activity without querying S3.

Usage from any service/router:
    from services.analytics import track
    track("match_finished", {"match_id": "abc", "user_id": "xyz", ...})
"""

import json
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from core.aws import get_s3_client
from core.config import get_settings

# ── Configuration ────────────────────────────────────────────────────────────

_BUFFER_FLUSH_SIZE = 50          # flush to S3 when buffer reaches this size
_RING_BUFFER_MAX = 500           # keep last N events in memory for admin
_S3_PREFIX = "analytics/events"

# ── Internal state ───────────────────────────────────────────────────────────

_buffer: list[dict] = []
_lock = threading.Lock()
_ring: deque[dict] = deque(maxlen=_RING_BUFFER_MAX)

# Cumulative counters (in-memory, reset on restart — lightweight dashboard)
_counters: dict[str, int] = {}
_counters_lock = threading.Lock()


# ── Public API ───────────────────────────────────────────────────────────────

def track(event_type: str, data: dict[str, Any] | None = None) -> None:
    """Record an analytics event. Non-blocking, thread-safe."""
    now = datetime.now(timezone.utc)
    event = {
        "event": event_type,
        "ts": now.isoformat(),
        "data": data or {},
    }

    # Increment counter
    with _counters_lock:
        _counters[event_type] = _counters.get(event_type, 0) + 1

    with _lock:
        _ring.append(event)
        _buffer.append(event)
        if len(_buffer) >= _BUFFER_FLUSH_SIZE:
            _flush_locked()


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
    """Return cumulative event counters since last restart."""
    with _counters_lock:
        return dict(_counters)


def get_counter(event_type: str) -> int:
    with _counters_lock:
        return _counters.get(event_type, 0)


# ── S3 flushing ──────────────────────────────────────────────────────────────

def _flush_locked() -> None:
    """Flush buffer to S3. Must be called while holding _lock."""
    if not _buffer:
        return

    to_write = list(_buffer)
    _buffer.clear()

    # Fire-and-forget in a thread to avoid blocking the request
    t = threading.Thread(target=_write_to_s3, args=(to_write,), daemon=True)
    t.start()


def _write_to_s3(events: list[dict]) -> None:
    """Write a batch of events to S3 as a JSONL file."""
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
        # Analytics should never crash the app — silently discard on failure
        pass


# ── S3 listing for dashboard ────────────────────────────────────────────────

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
            from datetime import timedelta
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
