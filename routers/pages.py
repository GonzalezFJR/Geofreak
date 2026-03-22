"""HTML page routes."""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

_templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=_templates_dir)


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    """Landing page."""
    return templates.TemplateResponse("landing.html", {"request": request})


@router.get("/map", response_class=HTMLResponse)
async def map_viewer(request: Request):
    """Interactive map viewer."""
    return templates.TemplateResponse("map.html", {"request": request})
