"""Analytics service — buffer events in memory, flush to S3 as JSONL.

Counters are persisted to S3 so they survive container restarts.
The flush threshold is controlled by the ANALYTICS_FLUSH_SIZE env var.

Each flush writes one file to:
    s3://{bucket}/analytics/events/{YYYY}/{MM}/{DD}/{HH}-{uuid4}.jsonl

And updates the cumulative counters at:
    s3://{bucket}/analytics/counters.json

Usage from any service/router:
    from services.analytics import track
    track("match_finished", {"match_id": "abc", "user_id": "xyz", ...})
"""

import json
import threading
import uuid
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any

from core.aws import get_s3_client
from core.config import get_settings

# ── Configuration ────────────────────────────────────────────────────────────

_S3_PREFIX = "analytics/events"
_S3_COUNTERS_KEY = "analytics/counters.json"
_RING_BUFFER_MAX = 500

# ── Internal state ───────────────────────────────────────────────────────────

_buffer: list[dict] = []
_lock = threading.Lock()
_ring: deque[dict] = deque(maxlen=_RING_BUFFER_MAX)

# Cumulative counters (initialised from S3 on first use)
_counters: dict[str, int] = {}
_counters_lock = threading.Lock()

_s3_state_loaded = False
_s3_state_lock = threading.Lock()


# ── S3 state persistence ────────────────────────────────────────────────────

def _ensure_s3_state_loaded() -> None:
    """Lazy-load persisted counters from S3 on first use."""
    global _s3_state_loaded
    if _s3_state_loaded:
        return
    with _s3_state_lock:
        if _s3_state_loaded:
            return
        try:
            settings = get_settings()
            resp = get_s3_client().get_object(
                Bucket=settings.s3_bucket_name,
                Key=_S3_COUNTERS_KEY,
            )
            data = json.loads(resp["Body"].read().decode("utf-8"))
            persisted = data.get("counters", {})
            with _counters_lock:
                for k, v in persisted.items():
                    _counters[k] = _counters.get(k, 0) + int(v)
        except Exception:
            pass  # First run or S3 unavailable
        _s3_state_loaded = True


def _persist_counters_to_s3(counters_snapshot: dict[str, int]) -> None:
    """Write cumulative counters to S3."""
    try:
        settings = get_settings()
        now = datetime.now(timezone.utc)
        body = json.dumps({
            "counters": counters_snapshot,
            "updated_at": now.isoformat(),
        }, ensure_ascii=False)
        get_s3_client().put_object(
            Bucket=settings.s3_bucket_name,
            Key=_S3_COUNTERS_KEY,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
    except Exception:
        pass


# ── Public API ───────────────────────────────────────────────────────────────

def track(event_type: str, data: dict[str, Any] | None = None) -> None:
    """Record an analytics event. Non-blocking, thread-safe."""
    _ensure_s3_state_loaded()

    now = datetime.now(timezone.utc)
    event = {
        "event": event_type,
        "ts": now.isoformat(),
        "data": data or {},
    }

    with _counters_lock:
        _counters[event_type] = _counters.get(event_type, 0) + 1
        counters_snapshot = dict(_counters)

    with _lock:
        _ring.append(event)
        _buffer.append(event)
        flush_size = get_settings().analytics_flush_size
        if len(_buffer) >= flush_size:
            _flush_locked()

    # Persist counters on every track() so they survive container restarts
    threading.Thread(
        target=_persist_counters_to_s3, args=(counters_snapshot,), daemon=True
    ).start()


def flush() -> None:
    """Force-flush the current buffer to S3. Call on shutdown."""
    _ensure_s3_state_loaded()
    with _lock:
        _flush_locked()


def get_recent_events(limit: int = 50) -> list[dict]:
    """Return the most recent events from the ring buffer."""
    with _lock:
        items = list(_ring)
    return items[-limit:][::-1]  # newest first


def get_counters() -> dict[str, int]:
    """Return cumulative event counters (persisted + in-memory)."""
    _ensure_s3_state_loaded()
    with _counters_lock:
        return dict(_counters)


def get_counter(event_type: str) -> int:
    _ensure_s3_state_loaded()
    with _counters_lock:
        return _counters.get(event_type, 0)


# ── S3 flushing ──────────────────────────────────────────────────────────────

def _flush_locked() -> None:
    """Flush buffer to S3. Must be called while holding _lock."""
    if not _buffer:
        return

    to_write = list(_buffer)
    _buffer.clear()

    # Snapshot counters to persist alongside events
    with _counters_lock:
        counters_snapshot = dict(_counters)

    t = threading.Thread(
        target=_write_to_s3, args=(to_write, counters_snapshot), daemon=True
    )
    t.start()


def _write_to_s3(events: list[dict], counters_snapshot: dict[str, int]) -> None:
    """Write a batch of events to S3 as JSONL + persist counters."""
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
        pass

    # Persist counters (separate try so events still flush even if this fails)
    _persist_counters_to_s3(counters_snapshot)


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
