"""Game page routes."""

import json

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse

from core.auth import get_optional_user
from core.i18n import get_lang
from core.templates import templates
from services.games import GamesService
from services.dataset import DatasetService

router = APIRouter(prefix="/games", tags=["games"])

games_service = GamesService()
_dataset_service = DatasetService()

TEMPLATE_MAP = {
    "flags": "games/flags.html",
    "outline": "games/outline.html",
    "ordering": "games/ordering.html",
    "comparison": "games/comparison.html",
    "geostats": "games/geostats.html",
}

MAP_GAME_CONFIG: dict = {}


@router.get("/daily", response_class=HTMLResponse)
async def daily_challenge(request: Request, user=Depends(get_optional_user)):
    """Render the daily challenge page (comparison game with pre-generated questions)."""
    lang = get_lang(request)
    game = games_service.get_game("comparison")
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_data = game.copy()
    game_data["daily"] = True
    game_json = json.dumps(game_data, ensure_ascii=False)
    ctx = {"request": request, "game": game_data, "game_json": game_json, "user": user, "lang": lang}
    return templates.TemplateResponse("games/comparison.html", ctx)


@router.get("", response_class=HTMLResponse)
async def games_dashboard(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    games = games_service.get_games()
    return templates.TemplateResponse(
        "games/dashboard.html", {"request": request, "games": games, "user": user, "lang": lang}
    )


@router.get("/map-challenge", response_class=HTMLResponse)
async def map_challenge_config(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    game = games_service.get_game("map-challenge")
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    counts = _dataset_service.get_map_game_counts()
    gd = game.get("defaults", {}) if game else {}
    ctx = {
        "request": request, "game": game, "user": user, "lang": lang,
        "map_game_counts_json": json.dumps(counts, ensure_ascii=False),
        "secs_per_item_type":  gd.get("secs_per_item_type", 4),
        "secs_per_item_click": gd.get("secs_per_item_click", 6),
    }
    return templates.TemplateResponse("games/map_challenge_config.html", ctx)


@router.get("/map-challenge/play", response_class=HTMLResponse)
async def play_map_challenge(
    request: Request,
    dataset: str = "countries",
    mode: str = "type",
    continent: str = "all",
    entity_type: str = "all",
    city_filter: str = "capitals",
    city_continent: str = "all",
    user=Depends(get_optional_user),
):
    lang = get_lang(request)
    game = games_service.get_game("map-challenge")
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    game_json = json.dumps(game, ensure_ascii=False)
    ctx = {
        "request": request, "game": game, "game_json": game_json, "user": user, "lang": lang,
        "map_dataset": dataset,
        "map_mode": mode,
        "map_continent": continent,
        "map_entity_type": entity_type,
        "map_city_filter": city_filter,
        "map_city_continent": city_continent,
    }
    return templates.TemplateResponse("games/map_game.html", ctx)


@router.get("/{game_id}", response_class=HTMLResponse)
async def play_game(request: Request, game_id: str, user=Depends(get_optional_user)):
    lang = get_lang(request)
    game = games_service.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    template = TEMPLATE_MAP.get(game_id)
    if not template:
        raise HTTPException(status_code=404, detail="Game template not found")
    game_json = json.dumps(game, ensure_ascii=False)
    ctx = {"request": request, "game": game, "game_json": game_json, "user": user, "lang": lang}
    ctx.update(MAP_GAME_CONFIG.get(game_id, {}))
    return templates.TemplateResponse(template, ctx)
