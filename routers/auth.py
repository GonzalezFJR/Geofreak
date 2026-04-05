"""Auth routes — register, login, logout, me, email confirm, password reset."""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Form, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from core.auth import get_current_user, get_optional_user
from core.config import get_settings
from core.i18n import get_lang
from core.templates import templates
from services.auth import (
    create_access_token,
    create_refresh_token,
    create_email_confirm_token,
    create_password_reset_token,
    create_email_change_token,
    decode_token,
    hash_password,
    verify_password,
)
from services.users import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    update_user,
)
from services.email import send_welcome, send_password_reset, send_email_change_confirm, send_verify_email
from services.analytics import track
from services.user_stats import ensure_user_stats
from services.friendships import get_friends, get_pending_received, get_pending_sent
from services.matches import get_match
from services.rankings import get_user_ranking_position
from services.daily_rankings import get_user_daily_ranking_position, get_user_daily_stats
from services.scoring import ALL_GAME_TYPES

router = APIRouter(tags=["auth"])

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


# ── HTML pages ───────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    lang = get_lang(request)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": "", "lang": lang})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/", status_code=303)
    lang = get_lang(request)
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": "", "lang": lang})


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(get_current_user)):
    lang = get_lang(request)
    uid = user["user_id"]
    stats = ensure_user_stats(uid)
    friends_list = get_friends(uid)
    friends_count = len(friends_list)
    pending_in = get_pending_received(uid)
    pending_out = get_pending_sent(uid)

    # Enrich friends with usernames
    friends_list = _enrich_friends(friends_list, "friend_user_id")
    pending_in = _enrich_friends(pending_in, "friend_user_id")
    pending_out = _enrich_friends(pending_out, "friend_user_id")

    google_new = request.query_params.get("google_new") == "1"

    # Best scores per game type
    best_scores = _build_best_scores(stats)

    # Overall max score (across all games) and name
    from services.games import GamesService
    _LANG_SUFFIX = {"es": "", "en": "_en", "fr": "_fr", "it": "_it", "ru": "_ru"}
    suffix = _LANG_SUFFIX.get(lang, "_en")
    game_name_map = {}
    for g in GamesService().get_games():
        gid = g.get("id", "")
        gname = g.get(f"name{suffix}") or g.get("name") or gid
        game_name_map[gid] = gname

    max_score_game = ""
    max_score_value = 0
    by_game_raw = stats.get("stats_by_game") or {}
    for gt, gs in by_game_raw.items():
        bs = int(gs.get("best_score", 0))
        if bs > max_score_value:
            max_score_value = bs
            max_score_game = game_name_map.get(gt, gt)

    # Daily challenge stats
    daily_stats = get_user_daily_stats(uid)

    # Current play streak (consecutive days playing any game)
    recent = list(stats.get("recent_matches") or [])
    today = datetime.now(timezone.utc).date()
    played_dates = sorted({str(m.get("date", ""))[:10] for m in recent if m.get("date")}, reverse=True)
    play_streak = 0
    expected = today
    for d_str in played_dates:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d == expected:
            play_streak += 1
            expected = d - timedelta(days=1)
        elif d < expected:
            break

    # Processed data for charts (convert DynamoDB Decimals to native types)
    recent_matches_chart = [
        {"game_type": str(m.get("game_type", "")), "date": str(m.get("date", ""))[:10]}
        for m in (stats.get("recent_matches") or [])
        if m.get("date")
    ]
    game_counters = {
        gt: int(gs.get("matches", 0))
        for gt, gs in (stats.get("stats_by_game") or {}).items()
    }

    # Ranking positions
    from core.i18n import t
    ranking_positions = [
        {"label": t("prof.daily_ranking", lang), "position": get_user_daily_ranking_position(uid, "daily-absolute")},
        {"label": t("prof.season_ranking", lang), "position": get_user_ranking_position(uid, "season")},
        {"label": t("prof.absolute_ranking", lang), "position": get_user_ranking_position(uid, "absolute")},
    ]

    # Per-game ranking positions
    game_ranking_positions = []
    for g in GamesService().get_games():
        gid = g.get("id", "")
        if gid not in ALL_GAME_TYPES:
            continue
        gname = game_name_map.get(gid, gid)
        pos = get_user_ranking_position(uid, "game", gid)
        game_ranking_positions.append({"label": gname, "position": pos, "game_type": gid})

    return templates.TemplateResponse("auth/profile.html", {
        "request": request, "user": user, "stats": stats, "lang": lang,
        "friends_count": friends_count, "best_scores": best_scores,
        "recent_matches_chart": recent_matches_chart,
        "game_counters": game_counters,
        "ranking_positions": ranking_positions,
        "game_ranking_positions": game_ranking_positions,
        "friends": friends_list,
        "pending_in": pending_in,
        "pending_out": pending_out,
        "google_new": google_new,
        "play_streak": play_streak,
        "daily_stats": daily_stats,
        "max_score_value": max_score_value,
        "max_score_game": max_score_game,
    })


# ── Form actions ─────────────────────────────────────────────────────────────

@router.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    # Validate
    lang = get_lang(request)
    if not USERNAME_RE.match(username):
        return _render_register(request, "El nombre de usuario debe tener 3-20 caracteres alfanuméricos." if lang == "es" else "Username must be 3-20 alphanumeric characters.", lang)
    if not EMAIL_RE.match(email):
        return _render_register(request, "Email no válido." if lang == "es" else "Invalid email.", lang)
    if len(password) < 8:
        return _render_register(request, "La contraseña debe tener al menos 8 caracteres." if lang == "es" else "Password must be at least 8 characters.", lang)
    if password != password2:
        return _render_register(request, "Las contraseñas no coinciden." if lang == "es" else "Passwords do not match.", lang)

    # Check uniqueness
    if get_user_by_email(email):
        return _render_register(request, "Ya existe una cuenta con ese email." if lang == "es" else "An account with that email already exists.", lang)
    if get_user_by_username(username):
        return _render_register(request, "Ese nombre de usuario ya está en uso." if lang == "es" else "That username is already taken.", lang)

    # Create
    user = create_user(username, email, hash_password(password))
    track("user_registered", {"user_id": user["user_id"], "username": username})

    # Send welcome email with confirmation link
    token = create_email_confirm_token(user["user_id"])
    confirm_url = f"{get_settings().base_url}/confirm-email?token={token}"
    send_welcome(email, username, confirm_url, lang)

    # Issue tokens
    response = RedirectResponse("/", status_code=303)
    _set_auth_cookies(response, user["user_id"])
    return response


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    lang = get_lang(request)

    # Check admin credentials first
    settings = get_settings()
    if settings.admin_user and email == settings.admin_user and password == settings.admin_pass:
        request.session["authenticated"] = True
        return RedirectResponse("/admin", status_code=303)

    # Try email first, then username
    user = get_user_by_email(email)
    if not user:
        user = get_user_by_username(email)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Credenciales incorrectas." if lang == "es" else "Wrong credentials.", "lang": lang},
        )
    if user.get("status") != "active":
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Cuenta desactivada." if lang == "es" else "Account disabled.", "lang": lang},
        )

    track("session_started", {"user_id": user["user_id"]})
    update_user(user["user_id"], {"last_login": datetime.now(timezone.utc).isoformat()})
    response = RedirectResponse("/", status_code=303)
    _set_auth_cookies(response, user["user_id"])
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


# ── Email confirmation ───────────────────────────────────────────────────────

@router.get("/confirm-email", response_class=HTMLResponse)
async def confirm_email(request: Request, token: str = ""):
    lang = get_lang(request)
    payload = decode_token(token)
    if not payload or payload.get("type") != "email_confirm":
        return templates.TemplateResponse("auth/message.html", {
            "request": request, "lang": lang,
            "title": "auth.confirm_fail_title",
            "message": "auth.confirm_fail",
        })
    user = get_user_by_id(payload["sub"])
    if not user:
        return templates.TemplateResponse("auth/message.html", {
            "request": request, "lang": lang,
            "title": "auth.confirm_fail_title",
            "message": "auth.confirm_fail",
        })
    update_user(user["user_id"], {"email_verified": True})
    # Redirect to profile so the user can see the verified status immediately.
    # If not logged in, get_current_user will redirect them to /login.
    return RedirectResponse("/profile?verified=1", status_code=303)


# ── Resend email verification ───────────────────────────────────────────────

@router.post("/profile/resend-verification")
async def resend_verification(request: Request, user=Depends(get_current_user)):
    lang = get_lang(request)

    if user.get("email_verified"):
        return RedirectResponse("/profile", status_code=303)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resend_date = user.get("email_resend_date", "")
    resend_count = int(user.get("email_resend_count", 0)) if resend_date == today else 0

    if resend_date == today and resend_count >= 2:
        return RedirectResponse("/profile?verify_error=limit", status_code=303)

    token = create_email_confirm_token(user["user_id"])
    url = f"{get_settings().base_url}/confirm-email?token={token}"
    send_verify_email(user["email"], user["username"], url, lang)

    update_user(user["user_id"], {
        "email_resend_date": today,
        "email_resend_count": resend_count + 1,
    })
    return RedirectResponse("/profile?verify_sent=1", status_code=303)


# ── Password recovery ───────────────────────────────────────────────────────

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/profile", status_code=303)
    lang = get_lang(request)
    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request, "lang": lang, "sent": False, "error": "",
    })


@router.post("/forgot-password")
async def forgot_password(request: Request, email: str = Form(...)):
    lang = get_lang(request)
    user = get_user_by_email(email)
    if user:
        token = create_password_reset_token(user["user_id"])
        url = f"{get_settings().base_url}/reset-password?token={token}"
        send_password_reset(user["email"], user["username"], url, lang)
    # Always show "sent" to avoid user enumeration
    return templates.TemplateResponse("auth/forgot_password.html", {
        "request": request, "lang": lang, "sent": True, "error": "",
    })


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    lang = get_lang(request)
    payload = decode_token(token)
    if not payload or payload.get("type") != "password_reset":
        return templates.TemplateResponse("auth/message.html", {
            "request": request, "lang": lang,
            "title": "auth.reset_fail_title",
            "message": "auth.reset_fail",
        })
    return templates.TemplateResponse("auth/reset_password.html", {
        "request": request, "lang": lang, "token": token, "error": "",
    })


@router.post("/reset-password")
async def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    lang = get_lang(request)
    payload = decode_token(token)
    if not payload or payload.get("type") != "password_reset":
        return templates.TemplateResponse("auth/message.html", {
            "request": request, "lang": lang,
            "title": "auth.reset_fail_title",
            "message": "auth.reset_fail",
        })
    if len(password) < 8:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request, "lang": lang, "token": token,
            "error": "La contraseña debe tener al menos 8 caracteres." if lang == "es" else "Password must be at least 8 characters.",
        })
    if password != password2:
        return templates.TemplateResponse("auth/reset_password.html", {
            "request": request, "lang": lang, "token": token,
            "error": "Las contraseñas no coinciden." if lang == "es" else "Passwords do not match.",
        })
    update_user(payload["sub"], {"password_hash": hash_password(password)})
    return templates.TemplateResponse("auth/message.html", {
        "request": request, "lang": lang,
        "title": "auth.reset_ok_title",
        "message": "auth.reset_ok",
    })


# ── Profile: change username ────────────────────────────────────────────────

@router.post("/profile/change-username")
async def change_username(
    request: Request,
    new_username: str = Form(...),
    user=Depends(get_current_user),
):
    new_username = new_username.strip()
    if not USERNAME_RE.match(new_username):
        return RedirectResponse("/profile?un_error=invalid", status_code=303)
    if new_username == user["username"]:
        return RedirectResponse("/profile", status_code=303)
    if get_user_by_username(new_username):
        return RedirectResponse("/profile?un_error=taken", status_code=303)
    update_user(user["user_id"], {"username": new_username})
    return RedirectResponse("/profile?un_ok=1", status_code=303)


# ── Profile: change password ────────────────────────────────────────────────

@router.post("/profile/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password2: str = Form(...),
    user=Depends(get_current_user),
):
    lang = get_lang(request)
    if not verify_password(current_password, user.get("password_hash", "")):
        return RedirectResponse(f"/profile?pw_error=wrong_pw", status_code=303)
    if len(new_password) < 8:
        return RedirectResponse(f"/profile?pw_error=too_short", status_code=303)
    if new_password != new_password2:
        return RedirectResponse(f"/profile?pw_error=mismatch", status_code=303)
    update_user(user["user_id"], {"password_hash": hash_password(new_password)})
    return RedirectResponse("/profile?pw_ok=1", status_code=303)


# ── Profile: change email ───────────────────────────────────────────────────

@router.post("/profile/change-email")
async def change_email(
    request: Request,
    new_email: str = Form(...),
    user=Depends(get_current_user),
):
    lang = get_lang(request)
    if not EMAIL_RE.match(new_email):
        return RedirectResponse("/profile?em_error=invalid", status_code=303)
    if get_user_by_email(new_email):
        return RedirectResponse("/profile?em_error=taken", status_code=303)
    token = create_email_change_token(user["user_id"], new_email)
    url = f"{get_settings().base_url}/confirm-email-change?token={token}"
    send_email_change_confirm(new_email, user["username"], url, lang)
    return RedirectResponse("/profile?em_sent=1", status_code=303)


@router.get("/confirm-email-change", response_class=HTMLResponse)
async def confirm_email_change(request: Request, token: str = ""):
    lang = get_lang(request)
    payload = decode_token(token)
    if not payload or payload.get("type") != "email_change" or not payload.get("new_email"):
        return templates.TemplateResponse("auth/message.html", {
            "request": request, "lang": lang,
            "title": "auth.confirm_fail_title",
            "message": "auth.confirm_fail",
        })
    new_email = payload["new_email"]
    if get_user_by_email(new_email):
        return templates.TemplateResponse("auth/message.html", {
            "request": request, "lang": lang,
            "title": "auth.confirm_fail_title",
            "message": "auth.email_taken",
        })
    update_user(payload["sub"], {"email": new_email.lower(), "email_verified": True})
    return templates.TemplateResponse("auth/message.html", {
        "request": request, "lang": lang,
        "title": "auth.email_changed_title",
        "message": "auth.email_changed",
    })


# ── Avatar ───────────────────────────────────────────────────────────────────

@router.get("/avatar/{user_id}")
async def serve_avatar(user_id: str):
    """Serve a user's profile picture from S3 (no auth required)."""
    from services.avatars import get_avatar_stream
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404)
    stream = get_avatar_stream(user["email"])
    if not stream:
        raise HTTPException(status_code=404)
    return StreamingResponse(stream, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@router.post("/profile/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Receive a cropped image, resize if needed, store in S3."""
    from services.avatars import upload_avatar as _upload
    data = await file.read()
    _upload(user["email"], data)
    update_user(user["user_id"], {"has_avatar": True})
    return JSONResponse({"ok": True})


# ── API (JSON) ───────────────────────────────────────────────────────────────

@router.get("/api/auth/me")
async def api_me(user=Depends(get_current_user)):
    return _safe_user(user)


# ── Google OAuth ──────────────────────────────────────────────────────────────

import secrets
import urllib.parse
import httpx

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@router.get("/auth/google/login")
async def google_login(request: Request):
    """Redirect user to Google consent screen."""
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(500, "Google OAuth not configured")
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": f"{settings.base_url}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


@router.get("/auth/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Handle the callback from Google after user consents."""
    lang = get_lang(request)
    settings = get_settings()

    if error or not code:
        return RedirectResponse("/login", status_code=303)

    # Verify state to prevent CSRF
    saved_state = request.session.pop("oauth_state", None)
    if not saved_state or saved_state != state:
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "Invalid OAuth state.", "lang": lang,
        })

    # Exchange authorization code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": f"{settings.base_url}/auth/google/callback",
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            return templates.TemplateResponse("auth/login.html", {
                "request": request, "error": "Google authentication failed.", "lang": lang,
            })
        tokens = token_resp.json()

        # Get user info from Google
        userinfo_resp = await client.get(GOOGLE_USERINFO_URL, headers={
            "Authorization": f"Bearer {tokens['access_token']}",
        })
        if userinfo_resp.status_code != 200:
            return templates.TemplateResponse("auth/login.html", {
                "request": request, "error": "Could not get Google user info.", "lang": lang,
            })
        guser = userinfo_resp.json()

    google_email = guser.get("email", "").lower()
    if not google_email:
        return templates.TemplateResponse("auth/login.html", {
            "request": request, "error": "No email from Google.", "lang": lang,
        })

    # Check if user exists by email
    user = get_user_by_email(google_email)
    is_new_user = user is None

    if user:
        # Existing user — log them in
        if user.get("status") != "active":
            return templates.TemplateResponse("auth/login.html", {
                "request": request,
                "error": "Cuenta desactivada." if lang == "es" else "Account disabled.",
                "lang": lang,
            })
        track("session_started", {"user_id": user["user_id"], "method": "google"})
        update_user(user["user_id"], {
            "last_login": datetime.now(timezone.utc).isoformat(),
            "email_verified": True,
        })
    else:
        # New user — create account
        google_name = guser.get("name", "").replace(" ", "_").lower()
        # Generate unique username from Google name
        base_username = re.sub(r'[^a-zA-Z0-9_]', '', google_name)[:15] or "user"
        username = base_username
        suffix = 1
        while get_user_by_username(username):
            username = f"{base_username}{suffix}"
            suffix += 1

        user = create_user(
            username=username,
            email=google_email,
            password_hash="",  # no password for Google-only users
            language=lang,
        )
        update_user(user["user_id"], {"email_verified": True, "auth_provider": "google"})
        track("user_registered", {"user_id": user["user_id"], "username": username, "method": "google"})

    redirect_url = "/?google_new=1" if is_new_user else "/"
    response = RedirectResponse(redirect_url, status_code=303)
    _set_auth_cookies(response, user["user_id"])
    return response


# ── Helpers ──────────────────────────────────────────────────────────────────

def _set_auth_cookies(response, user_id: str):
    settings = get_settings()
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    response.set_cookie(
        "access_token", access,
        httponly=True, samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )
    response.set_cookie(
        "refresh_token", refresh,
        httponly=True, samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
    )


def _safe_user(user: dict) -> dict:
    """Strip sensitive fields before returning to client."""
    exclude = {"password_hash"}
    return {k: v for k, v in user.items() if k not in exclude}


def _render_register(request: Request, error: str, lang: str = "es"):
    return templates.TemplateResponse(
        "auth/register.html", {"request": request, "error": error, "lang": lang}
    )


def _build_best_scores(stats: dict) -> list[dict]:
    """Build a list of best scores per game type from stats_by_game."""
    result = []
    by_game = stats.get("stats_by_game") or {}
    for game_type, gs in by_game.items():
        if int(gs.get("matches", 0)) > 0:
            result.append({
                "game_type": game_type,
                "best_score": int(gs.get("best_score", 0)),
                "best_accuracy": float(gs.get("best_accuracy", gs.get("total_accuracy", 0))),
                "best_time": gs.get("best_time", ""),
                "matches": int(gs.get("matches", 0)),
            })
    result.sort(key=lambda m: m.get("best_score", 0), reverse=True)
    return result


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
