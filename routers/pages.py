"""HTML page routes."""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.auth import get_optional_user
from core.config import get_settings
from core.i18n import get_lang, SUPPORTED_LANGS
from core.templates import templates
from services.email import send_contact
from services.games import GamesService
from services.analytics import track
from services.leaderboards import (
    get_leaderboard,
    get_user_position,
    GAME_TYPES,
)
from services.quiz import get_sources, get_all_variables

log = logging.getLogger(__name__)
router = APIRouter()
_games_svc = GamesService()
_settings = get_settings()

# Game types shown in each selection page
_PLAY_TYPES = {"solo"}             # ordering + comparison
_QUIZZ_TYPES = {"quiz", "map"}    # flags, outline, name-*


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    track("page_view", {"page": "landing"})
    return templates.TemplateResponse("landing.html", {
        "request": request, "user": user, "lang": lang,
    })


@router.get("/map", response_class=HTMLResponse)
async def map_viewer(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    track("page_view", {"page": "map"})
    can_edit = False
    if request.session.get("authenticated", False):
        can_edit = True  # Admin
    elif user:
        from services.users import get_user_role
        can_edit = get_user_role(user) == "editor"
    return templates.TemplateResponse("map.html", {"request": request, "user": user, "lang": lang, "can_edit": can_edit})


@router.get("/relief", response_class=HTMLResponse)
async def relief_map(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    track("page_view", {"page": "relief"})
    return templates.TemplateResponse("relief.html", {"request": request, "user": user, "lang": lang})


@router.get("/ranking", response_class=HTMLResponse)
async def ranking_page(
    request: Request,
    tab: str = Query("global", regex="^(global|game)$"),
    metric: str = Query("rating", regex="^(rating|total_matches|best_streak|best_score)$"),
    game: Optional[str] = Query(None),
    user=Depends(get_optional_user),
):
    lang = get_lang(request)
    track("page_view", {"page": "ranking"})

    # Load the requested leaderboard
    if tab == "game" and game and game in GAME_TYPES:
        lb = get_leaderboard("game", game, "best_score")
    else:
        lb = get_leaderboard("global", "all", metric)
        tab = "global"

    entries = lb["entries"] if lb else []
    updated_at = lb["updated_at"] if lb else None

    user_pos = None
    if user:
        if tab == "game" and game:
            user_pos = get_user_position(user["user_id"], "game", game, "best_score")
        else:
            user_pos = get_user_position(user["user_id"], "global", "all", metric)

    return templates.TemplateResponse("ranking.html", {
        "request": request, "user": user, "lang": lang,
        "tab": tab, "metric": metric, "game_type": game or "",
        "entries": entries, "updated_at": updated_at,
        "user_position": user_pos, "game_types": GAME_TYPES,
    })


@router.get("/play/{mode}", response_class=HTMLResponse)
async def play_select(request: Request, mode: str, user=Depends(get_optional_user)):
    if mode not in ("solo", "duel", "tournament"):
        mode = "solo"
    lang = get_lang(request)
    games = [g.copy() for g in _games_svc.get_games() if g.get("type") in _PLAY_TYPES and g.get("enabled")]
    href_prefix = {"solo": "/games/", "duel": "/duel/", "tournament": "/tournaments?game="}
    for g in games:
        g["_href"] = href_prefix[mode] + g["id"]
    return templates.TemplateResponse("games/select.html", {
        "request": request, "user": user, "lang": lang, "mode": mode, "games": games,
    })


@router.get("/quizz", response_class=HTMLResponse)
async def quizz_select(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    games = [g.copy() for g in _games_svc.get_games() if g.get("type") in _QUIZZ_TYPES and g.get("enabled")]
    for g in games:
        g["_href"] = "/games/" + g["id"]
    return templates.TemplateResponse("games/select.html", {
        "request": request, "user": user, "lang": lang, "mode": "quizz", "games": games,
    })


@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    return templates.TemplateResponse("contact.html", {
        "request": request, "user": user, "lang": lang,
        "sent": False, "error": False,
        "captcha_site_key": _settings.captcha_site_key,
    })


@router.post("/contact", response_class=HTMLResponse)
async def contact_submit(
    request: Request,
    name: str = Form(..., max_length=100),
    email: str = Form(..., max_length=200),
    message: str = Form(..., max_length=2000),
    user=Depends(get_optional_user),
):
    lang = get_lang(request)
    ctx = {
        "request": request, "user": user, "lang": lang,
        "captcha_site_key": _settings.captcha_site_key,
    }

    # Verify Turnstile captcha if configured
    if _settings.captcha_secret_key:
        form = await request.form()
        token = form.get("cf-turnstile-response", "")
        if not await _verify_turnstile(token, request.client.host if request.client else ""):
            log.warning("Captcha verification failed for contact form")
            return templates.TemplateResponse("contact.html", {**ctx, "sent": False, "error": True})

    ok = send_contact(name, email, message)
    return templates.TemplateResponse("contact.html", {**ctx, "sent": ok, "error": not ok})


async def _verify_turnstile(token: str, ip: str) -> bool:
    """Verify Turnstile token with Cloudflare API."""
    if not token:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret": _settings.captcha_secret_key,
                    "response": token,
                    "remoteip": ip,
                },
                timeout=10.0,
            )
            result = resp.json()
            return result.get("success", False)
    except Exception as e:
        log.error(f"Turnstile verification error: {e}")
        return False


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    sources = get_sources()
    variables = get_all_variables()
    return templates.TemplateResponse("sources.html", {
        "request": request, "user": user, "lang": lang,
        "sources": sources, "variables": variables,
    })


@router.get("/set-lang/{lang}")
async def set_language(request: Request, lang: str):
    """Set language cookie and redirect back."""
    lang = lang if lang in SUPPORTED_LANGS else "es"
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(referer, status_code=303)
    response.set_cookie("lang", lang, max_age=365 * 86400, samesite="lax")
    return response
