"""User repository — DynamoDB CRUD for geofreak_users."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key

from core.aws import get_dynamodb_resource
from core.config import get_settings


def _table():
    return get_dynamodb_resource().Table(get_settings().table_name("users"))


# ── Create ───────────────────────────────────────────────────────────────────

def create_user(username: str, email: str, password_hash: str, language: str = "es") -> dict:
    """Insert a new user. Returns the created item."""
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": str(uuid.uuid4()),
        "username": username,
        "email": email.lower(),
        "password_hash": password_hash,
        "created_at": now,
        "updated_at": now,
        "plan": "free",
        "status": "active",
        "country": "",
        "language": language,
        "settings": {},
    }
    _table().put_item(Item=item)
    return item


# ── Read ─────────────────────────────────────────────────────────────────────

def get_user_by_id(user_id: str) -> Optional[dict]:
    resp = _table().get_item(Key={"user_id": user_id})
    return resp.get("Item")


def get_user_by_email(email: str) -> Optional[dict]:
    resp = _table().query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email.lower()),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_user_by_username(username: str) -> Optional[dict]:
    resp = _table().query(
        IndexName="username-index",
        KeyConditionExpression=Key("username").eq(username),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


# ── Update ───────────────────────────────────────────────────────────────────

def update_user(user_id: str, updates: dict) -> Optional[dict]:
    """Update arbitrary fields on a user. Returns updated item."""
    if not updates:
        return get_user_by_id(user_id)

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    expr_parts = []
    names = {}
    values = {}
    for i, (k, v) in enumerate(updates.items()):
        alias = f"#k{i}"
        placeholder = f":v{i}"
        expr_parts.append(f"{alias} = {placeholder}")
        names[alias] = k
        values[placeholder] = v

    resp = _table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


# ── Delete ───────────────────────────────────────────────────────────────────

def delete_user(user_id: str) -> None:
    """Permanently delete a user from the database."""
    _table().delete_item(Key={"user_id": user_id})
