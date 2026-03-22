"""Game page routes."""

import json
import os

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services.games import GamesService

router = APIRouter(prefix="/games", tags=["games"])

_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_templates_dir)
games_service = GamesService()

TEMPLATE_MAP = {
    "flags": "games/flags.html",
    "outline": "games/outline.html",
    "name-countries-map": "games/name_countries_map.html",
    "name-countries-type": "games/name_countries_type.html",
    "name-capitals-map": "games/name_capitals_map.html",
    "name-capitals-type": "games/name_capitals_type.html",
}


@router.get("", response_class=HTMLResponse)
async def games_dashboard(request: Request):
    games = games_service.get_games()
    return templates.TemplateResponse(
        "games/dashboard.html", {"request": request, "games": games}
    )


@router.get("/{game_id}", response_class=HTMLResponse)
async def play_game(request: Request, game_id: str):
    game = games_service.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    template = TEMPLATE_MAP.get(game_id)
    if not template:
        raise HTTPException(status_code=404, detail="Game template not found")
    game_json = json.dumps(game, ensure_ascii=False)
    return templates.TemplateResponse(
        template, {"request": request, "game": game, "game_json": game_json}
    )
