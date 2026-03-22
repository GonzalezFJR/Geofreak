"""Admin routes — login & game configuration dashboard."""

import json
import os

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services.games import GamesService

router = APIRouter(prefix="/admin", tags=["admin"])

_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_templates_dir)
games_service = GamesService()


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated", False)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": ""})


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    admin_user = os.getenv("ADMIN_USER", "")
    admin_pass = os.getenv("ADMIN_PASS", "")
    if admin_user and username == admin_user and password == admin_pass:
        request.session["authenticated"] = True
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        "admin/login.html", {"request": request, "error": "Credenciales incorrectas"}
    )


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    games = games_service.get_games()
    return templates.TemplateResponse(
        "admin/dashboard.html", {"request": request, "games": games}
    )


@router.post("/games/{game_id}")
async def update_game(request: Request, game_id: str):
    if not is_authenticated(request):
        raise HTTPException(status_code=403, detail="Not authenticated")
    form = await request.form()
    updates = {
        "name": form.get("name", ""),
        "description": form.get("description", ""),
    }
    defaults = {}
    if form.get("time_limit"):
        defaults["time_limit"] = int(form.get("time_limit", 600))
    if form.get("max_items"):
        defaults["max_items"] = int(form.get("max_items", 30))
    if defaults:
        updates["defaults"] = defaults
    games_service.update_game(game_id, updates)
    return RedirectResponse("/admin", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
