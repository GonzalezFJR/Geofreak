"""Friendships service — DynamoDB CRUD for geofreak_friendships.

Table schema:
  PK = user_id (HASH)
  SK = friend_user_id (RANGE)

Each friendship is stored as TWO rows (bidirectional) so queries
from either side work with a simple query on PK.
"""

from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key

from core.aws import get_dynamodb_resource
from core.config import get_settings


def _table():
    return get_dynamodb_resource().Table(get_settings().table_name("friendships"))


# ── Create / Accept ─────────────────────────────────────────────────────────

def send_friend_request(from_user_id: str, to_user_id: str) -> dict:
    """Create a pending friendship request (one-directional until accepted)."""
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": from_user_id,
        "friend_user_id": to_user_id,
        "status": "pending_sent",
        "created_at": now,
    }
    _table().put_item(Item=item)
    # Mirror row for the target (so they can query their pending)
    mirror = {
        "user_id": to_user_id,
        "friend_user_id": from_user_id,
        "status": "pending_received",
        "created_at": now,
    }
    _table().put_item(Item=mirror)
    return item


def accept_friend_request(user_id: str, friend_user_id: str) -> bool:
    """Accept a pending request. Updates both rows to 'accepted'."""
    now = datetime.now(timezone.utc).isoformat()
    # Only accept if current status is pending_received
    row = get_friendship(user_id, friend_user_id)
    if not row or row.get("status") != "pending_received":
        return False

    _table().update_item(
        Key={"user_id": user_id, "friend_user_id": friend_user_id},
        UpdateExpression="SET #s = :s, accepted_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "accepted", ":now": now},
    )
    _table().update_item(
        Key={"user_id": friend_user_id, "friend_user_id": user_id},
        UpdateExpression="SET #s = :s, accepted_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "accepted", ":now": now},
    )
    return True


def reject_friend_request(user_id: str, friend_user_id: str) -> bool:
    """Reject / cancel a pending request. Deletes both rows."""
    row = get_friendship(user_id, friend_user_id)
    if not row or row.get("status") not in ("pending_received", "pending_sent"):
        return False
    _delete_pair(user_id, friend_user_id)
    return True


def remove_friend(user_id: str, friend_user_id: str) -> bool:
    """Remove an accepted friendship."""
    row = get_friendship(user_id, friend_user_id)
    if not row or row.get("status") != "accepted":
        return False
    _delete_pair(user_id, friend_user_id)
    return True


# ── Read ─────────────────────────────────────────────────────────────────────

def get_friendship(user_id: str, friend_user_id: str) -> Optional[dict]:
    resp = _table().get_item(Key={"user_id": user_id, "friend_user_id": friend_user_id})
    return resp.get("Item")


def get_friends(user_id: str) -> list[dict]:
    """Accepted friends for a user."""
    resp = _table().query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression="#s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "accepted"},
    )
    return resp.get("Items", [])


def get_pending_received(user_id: str) -> list[dict]:
    """Incoming friend requests."""
    resp = _table().query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression="#s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "pending_received"},
    )
    return resp.get("Items", [])


def get_pending_sent(user_id: str) -> list[dict]:
    """Outgoing friend requests that haven't been answered."""
    resp = _table().query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        FilterExpression="#s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "pending_sent"},
    )
    return resp.get("Items", [])


def count_pending(user_id: str) -> int:
    """Number of pending incoming requests (for badge)."""
    return len(get_pending_received(user_id))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _delete_pair(user_id: str, friend_user_id: str):
    _table().delete_item(Key={"user_id": user_id, "friend_user_id": friend_user_id})
    _table().delete_item(Key={"user_id": friend_user_id, "friend_user_id": user_id})
