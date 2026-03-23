"""HTML page routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.auth import get_optional_user
from core.i18n import get_lang, SUPPORTED_LANGS
from core.templates import templates
from services.leaderboards import (
    get_leaderboard,
    get_user_position,
    GAME_TYPES,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    # Fetch top-10 for the landing widget
    lb = get_leaderboard("global", "all", "rating")
    top10 = (lb["entries"] if lb else [])[:10]
    user_pos = None
    if user and lb:
        user_pos = get_user_position(user["user_id"])
    return templates.TemplateResponse("landing.html", {
        "request": request, "user": user, "lang": lang,
        "top10": top10, "user_position": user_pos,
    })


@router.get("/map", response_class=HTMLResponse)
async def map_viewer(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    return templates.TemplateResponse("map.html", {"request": request, "user": user, "lang": lang})


@router.get("/ranking", response_class=HTMLResponse)
async def ranking_page(
    request: Request,
    tab: str = Query("global", regex="^(global|game)$"),
    metric: str = Query("rating", regex="^(rating|total_matches|best_streak|best_score)$"),
    game: Optional[str] = Query(None),
    user=Depends(get_optional_user),
):
    lang = get_lang(request)

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


@router.get("/set-lang/{lang}")
async def set_language(request: Request, lang: str):
    """Set language cookie and redirect back."""
    lang = lang if lang in SUPPORTED_LANGS else "es"
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(referer, status_code=303)
    response.set_cookie("lang", lang, max_age=365 * 86400, samesite="lax")
    return response
