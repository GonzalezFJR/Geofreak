"""Social routes — friends page, friend actions (API), user search."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
    return RedirectResponse("/profile#friends", status_code=303)


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

    # Ranking positions
    from core.i18n import t
    from services.rankings import get_user_ranking_position
    from services.scoring import ALL_GAME_TYPES
    from services.daily_rankings import get_user_daily_ranking_position
    from services.games import GamesService
    from services.daily_challenge import get_user_daily_result

    uid = target["user_id"]
    ranking_positions = [
        {"label": t("prof.daily_ranking", lang), "position": get_user_daily_ranking_position(uid, "daily-absolute")},
        {"label": t("prof.season_ranking", lang), "position": get_user_ranking_position(uid, "season")},
        {"label": t("prof.absolute_ranking", lang), "position": get_user_ranking_position(uid, "absolute")},
    ]

    # Per-game ranking positions
    _LANG_SUFFIX = {"es": "", "en": "_en", "fr": "_fr", "it": "_it", "ru": "_ru"}
    suffix = _LANG_SUFFIX.get(lang, "_en")
    game_ranking_positions = []
    for g in GamesService().get_games():
        gid = g.get("id", "")
        if gid not in ALL_GAME_TYPES:
            continue
        gname = g.get(f"name{suffix}") or g.get("name") or gid
        pos = get_user_ranking_position(uid, "game", gid)
        game_ranking_positions.append({"label": gname, "position": pos, "game_type": gid})

    # Daily challenge result
    daily_result = get_user_daily_result(uid)

    return templates.TemplateResponse("social/public_profile.html", {
        "request": request,
        "user": user,
        "lang": lang,
        "profile": target,
        "stats": stats,
        "friends_count": len(friends_list),
        "friendship_status": friendship_status,
        "ranking_positions": ranking_positions,
        "game_ranking_positions": game_ranking_positions,
        "daily_result": daily_result,
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
    """Search users by exact username, exact email, or username contains."""
    from services.users import get_user_by_email

    current_id = user["user_id"] if user else None
    q_stripped = q.strip()

    # 1) Exact email match (if query looks like an email)
    if "@" in q_stripped:
        found = get_user_by_email(q_stripped)
        if found and found.get("user_id") != current_id:
            return {"results": [{
                "user_id": found["user_id"],
                "username": found["username"],
                "created_at": found.get("created_at", ""),
            }]}
        return {"results": []}

    # 2) Exact username match via GSI (fast)
    exact = get_user_by_username(q_stripped)
    results = []
    seen_ids = set()
    if exact and exact.get("user_id") != current_id:
        results.append({
            "user_id": exact["user_id"],
            "username": exact["username"],
            "created_at": exact.get("created_at", ""),
        })
        seen_ids.add(exact["user_id"])

    # 3) Username contains scan (paginated, capped at 200 items read)
    from boto3.dynamodb.conditions import Attr
    from core.aws import get_dynamodb_resource
    from core.config import get_settings

    table = get_dynamodb_resource().Table(get_settings().table_name("users"))
    q_low = q_stripped.lower()
    scan_kwargs = {
        "FilterExpression": Attr("username").contains(q_low) | Attr("username").contains(q_stripped),
        "ProjectionExpression": "user_id, username, created_at",
    }
    items_read = 0
    max_read = 200
    scan_results = []
    while items_read < max_read:
        resp = table.scan(**scan_kwargs)
        scan_results.extend(resp.get("Items", []))
        items_read += resp.get("ScannedCount", 0)
        if "LastEvaluatedKey" not in resp or items_read >= max_read:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    # Sort by relevance (exact first, then prefix, then contains)
    def sort_key(item):
        name = item.get("username", "").lower()
        if name == q_low:
            return (0, name)
        if name.startswith(q_low):
            return (1, name)
        return (2, name)

    scan_results.sort(key=sort_key)

    for r in scan_results:
        uid = r.get("user_id")
        if uid and uid != current_id and uid not in seen_ids:
            results.append(r)
            seen_ids.add(uid)
        if len(results) >= 10:
            break

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
