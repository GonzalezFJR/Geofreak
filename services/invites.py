"""Invites service — DynamoDB CRUD for geofreak_invites.

Table schema:
  PK = invite_id (HASH)
  GSI target-user-index: PK = target_user_id

Invite types: "friend", "duel", "tournament"
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from boto3.dynamodb.conditions import Key

from core.aws import get_dynamodb_resource
from core.config import get_settings


_DEFAULT_EXPIRY_HOURS = 72


def _table():
    return get_dynamodb_resource().Table(get_settings().table_name("invites"))


# ── Create ───────────────────────────────────────────────────────────────────

def create_invite(
    invite_type: str,
    created_by: str,
    target_user_id: str = "",
    invite_code: str = "",
    metadata: dict | None = None,
    expires_hours: int = _DEFAULT_EXPIRY_HOURS,
) -> dict:
    """Create a new invite. Returns the invite item."""
    now = datetime.now(timezone.utc)
    item = {
        "invite_id": str(uuid.uuid4()),
        "type": invite_type,
        "created_by": created_by,
        "target_user_id": target_user_id,
        "invite_code": invite_code or str(uuid.uuid4())[:8],
        "status": "pending",
        "metadata": metadata or {},
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=expires_hours)).isoformat(),
    }
    _table().put_item(Item=item)
    return item


# ── Read ─────────────────────────────────────────────────────────────────────

def get_invite(invite_id: str) -> Optional[dict]:
    resp = _table().get_item(Key={"invite_id": invite_id})
    return resp.get("Item")


def get_invites_for_user(target_user_id: str) -> list[dict]:
    """All pending invites targeting a user (via GSI)."""
    resp = _table().query(
        IndexName="target-user-index",
        KeyConditionExpression=Key("target_user_id").eq(target_user_id),
    )
    items = resp.get("Items", [])
    now = datetime.now(timezone.utc).isoformat()
    return [i for i in items if i.get("status") == "pending" and i.get("expires_at", "") > now]


def get_invites_sent_by(created_by: str) -> list[dict]:
    """All pending invites created by a user (scan with filter — OK for MVP)."""
    resp = _table().scan(
        FilterExpression="#cb = :cb AND #s = :s",
        ExpressionAttributeNames={"#cb": "created_by", "#s": "status"},
        ExpressionAttributeValues={":cb": created_by, ":s": "pending"},
    )
    return resp.get("Items", [])


# ── Update ───────────────────────────────────────────────────────────────────

def update_invite_status(invite_id: str, new_status: str) -> Optional[dict]:
    """Set status to 'accepted', 'rejected', or 'expired'."""
    resp = _table().update_item(
        Key={"invite_id": invite_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": new_status},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")
