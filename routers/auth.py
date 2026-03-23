"""Auth routes — register, login, logout, me."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from core.auth import get_current_user, get_optional_user
from core.config import get_settings
from core.i18n import get_lang
from core.templates import templates
from services.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from services.users import (
    create_user,
    get_user_by_email,
    get_user_by_username,
)
from services.analytics import track
from services.user_stats import ensure_user_stats
from services.friendships import get_friends
from services.matches import get_match

router = APIRouter(tags=["auth"])

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


# ── HTML pages ───────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/profile", status_code=303)
    lang = get_lang(request)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": "", "lang": lang})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse("/profile", status_code=303)
    lang = get_lang(request)
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": "", "lang": lang})


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(get_current_user)):
    lang = get_lang(request)
    stats = ensure_user_stats(user["user_id"])
    friends_list = get_friends(user["user_id"])
    friends_count = len(friends_list)

    # Recent matches from stats_by_game (last matches stored inline)
    recent_matches = _build_recent_matches(stats)

    return templates.TemplateResponse("auth/profile.html", {
        "request": request, "user": user, "stats": stats, "lang": lang,
        "friends_count": friends_count, "recent_matches": recent_matches,
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

    # Issue tokens
    response = RedirectResponse("/profile", status_code=303)
    _set_auth_cookies(response, user["user_id"])
    return response


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    user = get_user_by_email(email)
    lang = get_lang(request)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Email o contraseña incorrectos." if lang == "es" else "Wrong email or password.", "lang": lang},
        )
    if user.get("status") != "active":
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Cuenta desactivada." if lang == "es" else "Account disabled.", "lang": lang},
        )

    track("session_started", {"user_id": user["user_id"]})
    response = RedirectResponse("/profile", status_code=303)
    _set_auth_cookies(response, user["user_id"])
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


# ── API (JSON) ───────────────────────────────────────────────────────────────

@router.get("/api/auth/me")
async def api_me(user=Depends(get_current_user)):
    return _safe_user(user)


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


def _build_recent_matches(stats: dict) -> list[dict]:
    """Build a list of recent matches from stats_by_game + recent_matches."""
    # recent_matches stored in user_stats if available
    stored = stats.get("recent_matches")
    if stored and isinstance(stored, list):
        return stored[:20]

    # Fallback: synthesize from stats_by_game (one entry per game played)
    result = []
    by_game = stats.get("stats_by_game") or {}
    for game_type, gs in by_game.items():
        if int(gs.get("matches", 0)) > 0:
            result.append({
                "game_type": game_type,
                "score": int(gs.get("best_score", 0)),
                "accuracy": float(gs.get("total_accuracy", 0)),
                "date": stats.get("updated_at", ""),
            })
    result.sort(key=lambda m: m.get("date", ""), reverse=True)
    return result[:20]
