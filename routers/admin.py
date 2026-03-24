"""Admin routes — login, game config, users, analytics, datasets."""

import os

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from core.config import get_settings
from core.i18n import get_lang
from core.templates import templates
from services.analytics import get_counters, get_recent_events, count_s3_events_today, list_s3_event_files
from services.games import GamesService
from services.quiz import get_all_variables, get_sources, toggle_variable, reload_var_config

router = APIRouter(prefix="/admin", tags=["admin"])

games_service = GamesService()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data")


def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated", False)


def _require_auth(request: Request):
    if not is_authenticated(request):
        raise HTTPException(status_code=403, detail="Not authenticated")


# ── Auth ─────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin", status_code=303)
    lang = get_lang(request)
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": "", "lang": lang})


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    settings = get_settings()
    lang = get_lang(request)
    if settings.admin_user and username == settings.admin_user and password == settings.admin_pass:
        request.session["authenticated"] = True
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse(
        "admin/login.html", {"request": request, "error": "Credenciales incorrectas" if lang == "es" else "Invalid credentials", "lang": lang}
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


# ── Dashboard (games) ───────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)
    games = games_service.get_games()
    return templates.TemplateResponse(
        "admin/dashboard.html", {"request": request, "games": games, "lang": lang, "section": "games"}
    )


@router.post("/games/{game_id}")
async def update_game(request: Request, game_id: str):
    _require_auth(request)
    form = await request.form()
    updates = {
        "name": form.get("name", ""),
        "description": form.get("description", ""),
    }
    # Multilingual fields
    for suffix in ("en", "fr", "it", "ru"):
        for field in ("name", "description"):
            key = f"{field}_{suffix}"
            val = form.get(key, "")
            if val:
                updates[key] = val
    defaults = {}
    if form.get("time_limit"):
        defaults["time_limit"] = int(form.get("time_limit", 600))
    if form.get("max_items"):
        defaults["max_items"] = int(form.get("max_items", 30))
    if defaults:
        updates["defaults"] = defaults
    games_service.update_game(game_id, updates)
    return RedirectResponse("/admin", status_code=303)


# ── Users management ────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)

    from core.aws import get_dynamodb_resource
    settings = get_settings()
    table = get_dynamodb_resource().Table(settings.table_name("users"))
    resp = table.scan(Limit=200)
    users = resp.get("Items", [])
    # Sort by creation date descending
    users.sort(key=lambda u: u.get("created_at", ""), reverse=True)
    # Strip passwords
    for u in users:
        u.pop("password_hash", None)

    return templates.TemplateResponse(
        "admin/users.html", {"request": request, "users": users, "lang": lang, "section": "users"}
    )


@router.post("/users/{user_id}/status")
async def admin_toggle_user_status(request: Request, user_id: str):
    _require_auth(request)
    form = await request.form()
    new_status = form.get("status", "active")
    if new_status not in ("active", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")

    from services.users import update_user
    update_user(user_id, {"status": new_status})
    return RedirectResponse("/admin/users", status_code=303)


# ── Analytics ────────────────────────────────────────────────────────────────

@router.get("/analytics", response_class=HTMLResponse)
async def admin_analytics(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)

    counters = get_counters()
    recent = get_recent_events(limit=30)
    s3_today = count_s3_events_today()
    s3_files = list_s3_event_files(days=7, max_keys=50)

    # Compute some summary stats
    total_events = sum(counters.values())
    event_types = sorted(counters.items(), key=lambda x: x[1], reverse=True)

    return templates.TemplateResponse("admin/analytics.html", {
        "request": request, "lang": lang, "section": "analytics",
        "counters": counters, "total_events": total_events,
        "event_types": event_types, "recent": recent,
        "s3_today": s3_today, "s3_files": s3_files,
    })


# ── Datasets ─────────────────────────────────────────────────────────────────

@router.get("/datasets", response_class=HTMLResponse)
async def admin_datasets(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)

    datasets_info = []
    for fname in sorted(os.listdir(DATA_DIR)):
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            datasets_info.append({
                "name": fname,
                "size": size,
                "size_human": _human_size(size),
                "type": os.path.splitext(fname)[1].lstrip(".").upper() or "FILE",
            })

    # GeoJSON count
    geojson_dir = os.path.join(DATA_DIR, "geojson")
    geojson_count = 0
    geojson_size = 0
    if os.path.isdir(geojson_dir):
        for f in os.listdir(geojson_dir):
            fp = os.path.join(geojson_dir, f)
            if os.path.isfile(fp):
                geojson_count += 1
                geojson_size += os.path.getsize(fp)

    # Images counts
    images_dir = os.path.join(DATA_DIR, "images")
    images_count = 0
    if os.path.isdir(images_dir):
        images_count = len([f for f in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, f))])

    # Variables config
    variables = get_all_variables()
    sources = get_sources()

    return templates.TemplateResponse("admin/datasets.html", {
        "request": request, "lang": lang, "section": "datasets",
        "datasets": datasets_info,
        "geojson_count": geojson_count,
        "geojson_size_human": _human_size(geojson_size),
        "images_count": images_count,
        "variables": variables,
        "sources": sources,
    })


@router.post("/datasets/variables/{var_key}/toggle")
async def admin_toggle_variable(request: Request, var_key: str):
    _require_auth(request)
    form = await request.form()
    enabled = form.get("enabled") == "1"
    toggle_variable(var_key, enabled)
    return RedirectResponse("/admin/datasets", status_code=303)


def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
