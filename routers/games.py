"""Game page routes."""

import json

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse

from core.auth import get_optional_user
from core.i18n import get_lang
from core.templates import templates
from services.games import GamesService

router = APIRouter(prefix="/games", tags=["games"])

games_service = GamesService()

TEMPLATE_MAP = {
    "flags": "games/flags.html",
    "outline": "games/outline.html",
    "name-countries-map": "games/map_game.html",
    "name-countries-type": "games/map_game.html",
    "name-capitals-map": "games/map_game.html",
    "name-capitals-type": "games/map_game.html",
    "ordering": "games/ordering.html",
    "comparison": "games/comparison.html",
    "geostats": "games/geostats.html",
}

MAP_GAME_CONFIG = {
    "name-countries-map":  {"map_mode": "click", "map_target": "country"},
    "name-countries-type": {"map_mode": "type",  "map_target": "country"},
    "name-capitals-map":   {"map_mode": "click", "map_target": "capital"},
    "name-capitals-type":  {"map_mode": "type",  "map_target": "capital"},
}


@router.get("", response_class=HTMLResponse)
async def games_dashboard(request: Request, user=Depends(get_optional_user)):
    lang = get_lang(request)
    games = games_service.get_games()
    return templates.TemplateResponse(
        "games/dashboard.html", {"request": request, "games": games, "user": user, "lang": lang}
    )


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
