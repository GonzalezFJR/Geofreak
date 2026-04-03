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
from services.rankings import (
    get_game_ranking,
    get_game_season_ranking,
    get_season_ranking,
    get_absolute_ranking,
    get_user_ranking_position,
)
from services.daily_rankings import (
    get_daily_day_ranking,
    get_daily_monthly_ranking,
    get_daily_absolute_ranking,
    get_user_daily_ranking_position,
)
from services.scoring import ALL_GAME_TYPES
from services.quiz import get_sources, get_all_variables

log = logging.getLogger(__name__)
router = APIRouter()
_games_svc = GamesService()
_settings = get_settings()

# Language suffix map for contents.json game names
_LANG_SUFFIX = {"es": "", "en": "_en", "fr": "_fr", "it": "_it", "ru": "_ru"}


def _build_game_names(lang: str) -> dict[str, str]:
    """Map game_id → localized display name from contents.json."""
    suffix = _LANG_SUFFIX.get(lang, "_en")
    result = {}
    for g in _games_svc.get_games():
        gid = g.get("id", "")
        name = g.get(f"name{suffix}") or g.get("name") or gid
        result[gid] = name
    return result

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
    cat: Optional[str] = Query(None),
    sub: Optional[str] = Query(None),
    game: Optional[str] = Query(None),
    user=Depends(get_optional_user),
):
    lang = get_lang(request)
    track("page_view", {"page": "ranking"})

    game_types = sorted(ALL_GAME_TYPES)
    entries = []
    updated_at = None
    user_pos = None
    category = cat
    game_type = game or ""
    category_title = ""

    # Build game display names from contents.json
    game_names = _build_game_names(lang)

    if cat == "daily":
        sub = sub or "today"
        from core.i18n import t
        sub_labels = {"today": t("lb.today", lang), "monthly": t("lb.monthly", lang), "absolute": t("lb.absolute", lang)}
        category_title = t("lb.daily", lang) + " — " + sub_labels.get(sub, "")
        if sub == "today":
            lb = get_daily_day_ranking()
        elif sub == "monthly":
            lb = get_daily_monthly_ranking()
        elif sub == "absolute":
            lb = get_daily_absolute_ranking()
        else:
            lb = None
        entries = lb.get("entries", []) if lb else []
        updated_at = lb.get("updated_at") if lb else None
        if user:
            scope_map = {"today": "daily-day", "monthly": "daily-monthly", "absolute": "daily-absolute"}
            user_pos = get_user_daily_ranking_position(user["user_id"], scope_map.get(sub, "daily-day"))

    elif cat == "global":
        sub = sub or "season"
        from core.i18n import t
        sub_labels = {"season": t("lb.season", lang), "absolute": t("lb.absolute", lang)}
        category_title = t("lb.global_ranking", lang) + " — " + sub_labels.get(sub, "")
        if sub == "season":
            lb = get_season_ranking()
        elif sub == "absolute":
            lb = get_absolute_ranking()
        else:
            lb = None
        entries = lb.get("entries", []) if lb else []
        updated_at = lb.get("updated_at") if lb else None
        if user:
            user_pos = get_user_ranking_position(user["user_id"], sub)

    elif cat == "game":
        gt = game if game and game in ALL_GAME_TYPES else game_types[0]
        game_type = gt
        sub = sub or "absolute"
        from core.i18n import t
        sub_label = t("lb.season", lang) if sub == "season" else t("lb.absolute", lang)
        category_title = t("lb.by_game_ranking", lang) + " — " + game_names.get(gt, gt) + " — " + sub_label
        if sub == "season":
            lb = get_game_season_ranking(gt)
        else:
            lb = get_game_ranking(gt)
        entries = lb.get("entries", []) if lb else []
        updated_at = lb.get("updated_at") if lb else None
        if user:
            user_pos = get_user_ranking_position(user["user_id"], f"game-{sub}" if sub == "season" else "game", gt)
    else:
        category = None  # show category cards
        sub = None

    # Limit public ranking to top 20
    entries = entries[:20]

    return templates.TemplateResponse("ranking.html", {
        "request": request, "user": user, "lang": lang,
        "category": category, "sub": sub,
        "category_title": category_title,
        "game_type": game_type, "game_types": game_types,
        "game_names": game_names,
        "entries": entries, "updated_at": updated_at,
        "user_position": user_pos,
    })


@router.get("/play/{mode}", response_class=HTMLResponse)
async def play_select(request: Request, mode: str, user=Depends(get_optional_user)):
    if mode not in ("solo", "duel"):
        mode = "solo"
    lang = get_lang(request)
    games = [g.copy() for g in _games_svc.get_games() if g.get("type") in _PLAY_TYPES and g.get("enabled")]
    href_prefix = {"solo": "/games/", "duel": "/duel/"}
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
