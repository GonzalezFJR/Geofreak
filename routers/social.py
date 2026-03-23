"""Social routes — friends page, friend actions (API), user search."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from core.auth import get_current_user, get_optional_user
from core.i18n import get_lang
from core.templates import templates
from services.friendships import (
    send_friend_request,
    accept_friend_request,
    reject_friend_request,
    remove_friend,
    get_friends,
    get_pending_received,
    get_pending_sent,
    get_friendship,
    count_pending,
)
from services.users import get_user_by_id, get_user_by_username
from services.user_stats import ensure_user_stats

router = APIRouter(tags=["social"])


# ── HTML page ────────────────────────────────────────────────────────────────

@router.get("/friends", response_class=HTMLResponse)
async def friends_page(request: Request, user=Depends(get_current_user)):
    lang = get_lang(request)
    friends_list = get_friends(user["user_id"])
    pending_in = get_pending_received(user["user_id"])
    pending_out = get_pending_sent(user["user_id"])

    # Enrich with usernames
    friends_list = _enrich_friends(friends_list, "friend_user_id")
    pending_in = _enrich_friends(pending_in, "friend_user_id")
    pending_out = _enrich_friends(pending_out, "friend_user_id")

    return templates.TemplateResponse("social/friends.html", {
        "request": request,
        "user": user,
        "lang": lang,
        "friends": friends_list,
        "pending_in": pending_in,
        "pending_out": pending_out,
    })


# ── Public profile page (viewable by anyone) ────────────────────────────────

@router.get("/user/{username}", response_class=HTMLResponse)
async def public_profile(request: Request, username: str, user=Depends(get_optional_user)):
    lang = get_lang(request)
    target = get_user_by_username(username)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    stats = ensure_user_stats(target["user_id"])
    friends_list = get_friends(target["user_id"])

    # Friendship status with current viewer
    friendship_status = None
    if user and user["user_id"] != target["user_id"]:
        rel = get_friendship(user["user_id"], target["user_id"])
        friendship_status = rel.get("status") if rel else None

    return templates.TemplateResponse("social/public_profile.html", {
        "request": request,
        "user": user,
        "lang": lang,
        "profile": target,
        "stats": stats,
        "friends_count": len(friends_list),
        "friendship_status": friendship_status,
    })


# ── API: Friend actions ─────────────────────────────────────────────────────

class FriendActionPayload(BaseModel):
    target_user_id: str


@router.post("/api/friends/request")
async def api_friend_request(payload: FriendActionPayload, user=Depends(get_current_user)):
    """Send a friend request."""
    if payload.target_user_id == user["user_id"]:
        raise HTTPException(400, "Cannot add yourself")

    target = get_user_by_id(payload.target_user_id)
    if not target:
        raise HTTPException(404, "User not found")

    existing = get_friendship(user["user_id"], payload.target_user_id)
    if existing:
        status = existing.get("status")
        if status == "accepted":
            return {"ok": False, "reason": "already_friends"}
        if status in ("pending_sent", "pending_received"):
            return {"ok": False, "reason": "request_exists"}

    send_friend_request(user["user_id"], payload.target_user_id)
    return {"ok": True}


@router.post("/api/friends/accept")
async def api_friend_accept(payload: FriendActionPayload, user=Depends(get_current_user)):
    ok = accept_friend_request(user["user_id"], payload.target_user_id)
    if not ok:
        raise HTTPException(400, "No pending request")
    return {"ok": True}


@router.post("/api/friends/reject")
async def api_friend_reject(payload: FriendActionPayload, user=Depends(get_current_user)):
    ok = reject_friend_request(user["user_id"], payload.target_user_id)
    if not ok:
        raise HTTPException(400, "No pending request")
    return {"ok": True}


@router.post("/api/friends/remove")
async def api_friend_remove(payload: FriendActionPayload, user=Depends(get_current_user)):
    ok = remove_friend(user["user_id"], payload.target_user_id)
    if not ok:
        raise HTTPException(400, "Not friends")
    return {"ok": True}


# ── API: User search ────────────────────────────────────────────────────────

@router.get("/api/users/search")
async def api_user_search(
    q: str = Query(..., min_length=2, max_length=50),
    user: Optional[dict] = Depends(get_optional_user),
):
    """Search users by username prefix. Returns max 10 results."""
    from boto3.dynamodb.conditions import Key, Attr
    from core.aws import get_dynamodb_resource
    from core.config import get_settings

    table = get_dynamodb_resource().Table(get_settings().table_name("users"))

    # DynamoDB doesn't support LIKE/prefix on GSI easily.
    # For MVP: scan with filter (fine for < 10K users).
    resp = table.scan(
        FilterExpression=Attr("username").contains(q.lower()) | Attr("username").contains(q),
        ProjectionExpression="user_id, username, created_at",
        Limit=50,
    )
    results = resp.get("Items", [])

    # Sort by relevance (exact match first, then prefix, then contains)
    q_low = q.lower()
    def sort_key(item):
        name = item.get("username", "").lower()
        if name == q_low:
            return (0, name)
        if name.startswith(q_low):
            return (1, name)
        return (2, name)

    results.sort(key=sort_key)

    # Exclude current user if logged in
    current_id = user["user_id"] if user else None
    results = [r for r in results if r.get("user_id") != current_id][:10]

    return {"results": results}


# ── API: Pending count (for nav badge) ───────────────────────────────────────

@router.get("/api/friends/pending-count")
async def api_pending_count(user=Depends(get_current_user)):
    return {"count": count_pending(user["user_id"])}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _enrich_friends(items: list[dict], uid_field: str) -> list[dict]:
    """Add username, created_at to each friendship row."""
    for item in items:
        friend = get_user_by_id(item.get(uid_field, ""))
        if friend:
            item["username"] = friend.get("username", "???")
            item["friend_created_at"] = friend.get("created_at", "")
        else:
            item["username"] = "???"
            item["friend_created_at"] = ""
    return items
