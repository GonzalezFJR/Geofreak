"""Admin routes — login, game config, users, analytics, datasets, daily challenges."""

import csv
import json
import os
import subprocess
import sys

from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse

from core.config import get_settings
from core.i18n import get_lang
from core.templates import templates
from services.analytics import get_counters, get_recent_events, count_s3_events_today, list_s3_event_files
from services.games import GamesService
from services.quiz import get_all_variables, get_datasets, get_sources, toggle_variable, reload_var_config
from services.dataset_config import get_dataset_config_service

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
async def admin_dashboard(request: Request, saved: str = ""):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)
    games = games_service.get_games()
    return templates.TemplateResponse(
        "admin/dashboard.html", {"request": request, "games": games, "lang": lang, "section": "games", "saved": saved == "1"}
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
    # Visibility
    updates["visible"] = form.get("visible") == "1"

    # Build defaults — merge with existing to preserve unset fields
    game = games_service.get_game(game_id)
    defaults = dict(game.get("defaults", {})) if game else {}
    if form.get("max_items"):
        defaults["max_items"] = int(form.get("max_items", 20))
    if form.get("n_options"):
        try:
            defaults["n_options"] = [int(x.strip()) for x in str(form.get("n_options")).split(",") if x.strip().isdigit()]
        except (ValueError, TypeError):
            pass
    if form.get("secs_per_item"):
        try:
            defaults["secs_per_item"] = max(1, int(form.get("secs_per_item")))
        except (ValueError, TypeError):
            pass
    # Auto-compute time_limit from secs_per_item × max_items
    if defaults.get("secs_per_item") and defaults.get("max_items"):
        defaults["time_limit"] = defaults["secs_per_item"] * defaults["max_items"]
    if form.get("secs_per_item_type"):
        try:
            defaults["secs_per_item_type"] = max(1, int(form.get("secs_per_item_type")))
        except (ValueError, TypeError):
            pass
    if form.get("secs_per_item_click"):
        try:
            defaults["secs_per_item_click"] = max(1, int(form.get("secs_per_item_click")))
        except (ValueError, TypeError):
            pass
    if form.get("default_difficulty"):
        val = form.get("default_difficulty", "normal")
        if val in ("easy", "normal", "hard", "very_hard", "extreme"):
            defaults["default_difficulty"] = val
    if form.get("default_countdown"):
        val = form.get("default_countdown", "auto")
        if val in ("auto", "on", "off"):
            defaults["default_countdown"] = val
    updates["defaults"] = defaults

    # Game modes (solo-type games only)
    if game and game.get("type") == "solo":
        updates["modes"] = {
            "solo": form.get("mode_solo") == "1",
            "duel": form.get("mode_duel") == "1",
            "tournament": form.get("mode_tournament") == "1",
        }

    games_service.update_game(game_id, updates)
    return RedirectResponse("/admin?saved=1", status_code=303)


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


@router.post("/users/{user_id}/delete")
async def admin_delete_user(request: Request, user_id: str):
    _require_auth(request)
    from services.users import delete_user
    delete_user(user_id)
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}/details")
async def admin_user_details(request: Request, user_id: str):
    _require_auth(request)
    from decimal import Decimal
    from core.aws import get_dynamodb_resource
    from services.user_stats import get_user_stats
    from services.leaderboards import get_user_position

    settings = get_settings()
    table = get_dynamodb_resource().Table(settings.table_name("users"))
    resp = table.get_item(Key={"user_id": user_id})
    user = resp.get("Item", {})
    user.pop("password_hash", None)

    stats = get_user_stats(user_id) or {}
    stats.pop("user_id", None)
    stats.pop("stats_by_game", None)
    stats.pop("best_scores", None)
    stats.pop("best_times", None)
    stats.pop("recent_matches", None)

    def _conv(o):
        if isinstance(o, Decimal):
            return int(o)
        if isinstance(o, dict):
            return {k: _conv(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_conv(i) for i in o]
        return o

    user = _conv(user)
    stats = _conv(stats)

    try:
        rank_rating = get_user_position(user_id, "global", "all", "rating")
        rank_matches = get_user_position(user_id, "global", "all", "total_matches")
    except Exception:
        rank_rating = None
        rank_matches = None

    return JSONResponse({
        "user": user,
        "stats": {
            "total_matches": stats.get("total_matches", 0),
            "total_wins": stats.get("total_wins", 0),
            "total_losses": stats.get("total_losses", 0),
            "rating": stats.get("rating", 1000),
            "best_streak": stats.get("best_streak", 0),
            "updated_at": stats.get("updated_at", ""),
        },
        "rankings": {
            "rating": rank_rating,
            "total_matches": rank_matches,
        },
    })


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
async def admin_datasets(request: Request, dataset: str = Query("countries")):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)

    all_datasets = get_datasets()
    # Validate dataset param
    if dataset not in all_datasets:
        dataset = "countries"

    current_ds = all_datasets[dataset]

    # Files in static/data for this dataset
    datasets_info = []
    csv_file = current_ds.get("csv")
    if csv_file:
        fpath = os.path.join(DATA_DIR, csv_file)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            datasets_info.append({
                "name": csv_file,
                "size": size,
                "size_human": _human_size(size),
                "type": os.path.splitext(csv_file)[1].lstrip(".").upper(),
            })
    # Add config file
    config_path = os.path.join(DATA_DIR, "variable_config.json")
    if os.path.isfile(config_path):
        size = os.path.getsize(config_path)
        datasets_info.append({
            "name": "variable_config.json",
            "size": size,
            "size_human": _human_size(size),
            "type": "JSON",
        })
    # Add contents.json if exists
    contents_path = os.path.join(DATA_DIR, "contents.json")
    if os.path.isfile(contents_path):
        size = os.path.getsize(contents_path)
        datasets_info.append({
            "name": "contents.json",
            "size": size,
            "size_human": _human_size(size),
            "type": "JSON",
        })

    # GeoJSON for this dataset
    geojson_dir_name = current_ds.get("geojson_dir")
    geojson_count = 0
    geojson_size = 0
    if geojson_dir_name:
        geojson_dir = os.path.join(DATA_DIR, geojson_dir_name)
        if os.path.isdir(geojson_dir):
            for f in os.listdir(geojson_dir):
                fp = os.path.join(geojson_dir, f)
                if os.path.isfile(fp):
                    geojson_count += 1
                    geojson_size += os.path.getsize(fp)

    # Images for this dataset
    images_dir_name = current_ds.get("images_dir")
    images_count = 0
    if images_dir_name:
        images_dir = os.path.join(DATA_DIR, images_dir_name)
        if os.path.isdir(images_dir):
            images_count = len([f for f in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, f))])

    # Variables for this dataset
    variables = get_all_variables(dataset)
    sources = get_sources()

    # CSV summary
    csv_summary = None
    csv_file = current_ds.get("csv")
    if csv_file:
        csv_path = os.path.join(DATA_DIR, csv_file)
        if os.path.isfile(csv_path):
            csv_summary = _build_csv_summary(csv_path, current_ds)

    # Dataset list for selector
    dataset_list = []
    for ds_id, ds_info in all_datasets.items():
        dataset_list.append({
            "id": ds_id,
            "label_es": ds_info.get("label_es", ds_id),
            "label_en": ds_info.get("label_en", ds_id),
        })

    return templates.TemplateResponse("admin/datasets.html", {
        "request": request, "lang": lang, "section": "datasets",
        "datasets": datasets_info,
        "geojson_count": geojson_count,
        "geojson_size_human": _human_size(geojson_size),
        "images_count": images_count,
        "variables": variables,
        "sources": sources,
        "current_dataset": dataset,
        "dataset_list": dataset_list,
        "csv_summary": csv_summary,
    })


@router.post("/datasets/variables/{var_key}/toggle")
async def admin_toggle_variable(request: Request, var_key: str):
    _require_auth(request)
    form = await request.form()
    enabled = form.get("enabled") == "1"
    dataset_id = form.get("dataset", "countries")
    toggle_variable(var_key, enabled, dataset_id)
    return RedirectResponse(f"/admin/datasets?dataset={dataset_id}", status_code=303)


@router.get("/datasets/download/{filename}")
async def admin_download_file(request: Request, filename: str):
    _require_auth(request)
    # Security: only allow files directly in DATA_DIR (no path traversal)
    safe_name = os.path.basename(filename)
    fpath = os.path.join(DATA_DIR, safe_name)
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(fpath, filename=safe_name)


def _build_csv_summary(csv_path: str, ds_config: dict) -> dict:
    """Build a summary of the CSV file: rows, cols, numeric stats, and primary key values."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return {"rows": 0, "cols": 0, "columns": [], "numeric_stats": {}, "primary_keys": []}

    columns = list(rows[0].keys())
    name_field = ds_config.get("name_es_field") or ds_config.get("name_field") or columns[0]

    # Primary key values (entity names)
    primary_keys = []
    for row in rows:
        val = row.get(name_field, "")
        if val:
            primary_keys.append(val)

    # Numeric stats for numeric columns
    numeric_stats = {}
    for col in columns:
        vals = []
        for row in rows:
            try:
                v = row.get(col, "")
                if v not in ("", None):
                    vals.append(float(v))
            except (ValueError, TypeError):
                continue
        if len(vals) >= 2:
            vals.sort()
            numeric_stats[col] = {
                "count": len(vals),
                "min": vals[0],
                "max": vals[-1],
                "mean": sum(vals) / len(vals),
                "nulls": len(rows) - len(vals),
            }

    return {
        "rows": len(rows),
        "cols": len(columns),
        "columns": columns,
        "numeric_stats": numeric_stats,
        "primary_keys": primary_keys,
    }


def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ── Daily Challenges ─────────────────────────────────────────────────────────

_DC_S3_PREFIX = "daily_challenges"


def _list_daily_challenges_s3(max_keys: int = 200) -> list[dict]:
    """List daily challenge files in S3, enriched with metadata from _index.json."""
    from core.aws import get_s3_client
    settings = get_settings()
    s3 = get_s3_client()

    # Load metadata index (game_type, difficulty, num_questions per date)
    index: dict = {}
    try:
        resp = s3.get_object(Bucket=settings.s3_bucket_name, Key=f"{_DC_S3_PREFIX}/_index.json")
        index = json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        pass

    try:
        resp = s3.list_objects_v2(
            Bucket=settings.s3_bucket_name,
            Prefix=f"{_DC_S3_PREFIX}/",
            MaxKeys=max_keys,
        )
        files = []
        for obj in resp.get("Contents", []):
            key = obj["Key"]
            date_part = key.replace(f"{_DC_S3_PREFIX}/", "").replace(".json", "")
            if date_part == "_index":
                continue
            meta = index.get(date_part, {})
            files.append({
                "key": key,
                "date": date_part,
                "size": obj["Size"],
                "size_human": _human_size(obj["Size"]),
                "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else "",
                "game_type": meta.get("game_type", "comparison"),
                "difficulty": meta.get("difficulty", "—"),
                "num_questions": meta.get("num_questions", "—"),
            })
        files.sort(key=lambda f: f["date"])
        return files
    except Exception:
        return []


def _get_challenge_json_s3(date_str: str) -> dict | None:
    """Download and return a challenge JSON from S3."""
    from core.aws import get_s3_client
    settings = get_settings()
    s3 = get_s3_client()
    key = f"{_DC_S3_PREFIX}/{date_str}.json"
    try:
        resp = s3.get_object(Bucket=settings.s3_bucket_name, Key=key)
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)
    except Exception:
        return None


@router.get("/daily", response_class=HTMLResponse)
async def admin_daily(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)

    challenges = _list_daily_challenges_s3()
    # Split into past/today and future
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    future = [c for c in challenges if c["date"] >= today]
    past = [c for c in challenges if c["date"] < today]

    return templates.TemplateResponse("admin/daily.html", {
        "request": request, "lang": lang, "section": "daily",
        "challenges_future": future,
        "challenges_past": past,
        "today": today,
        "total_challenges": len(challenges),
    })


@router.post("/daily/generate")
async def admin_daily_generate(
    request: Request,
    game: str = Form("comparison"),
    mode: str = Form("range"),          # "range" | "dates"
    start: str = Form(""),
    days: int = Form(90),
    dates: str = Form(""),              # comma-separated specific dates
    difficulty: str = Form("normal"),
    num_questions: int = Form(10),
    secs_per_item: int = Form(15),
    countdown: str = Form("1"),         # "1" = yes, "0" = no
    no_overwrite: str = Form(""),       # checkbox: non-empty = skip existing
):
    _require_auth(request)
    from datetime import datetime, timezone

    if game not in ("comparison", "ordering", "geostats"):
        game = "comparison"
    if difficulty not in ("easy", "normal", "hard", "very_hard", "extreme"):
        difficulty = "normal"
    num_questions = max(1, min(50, num_questions))
    secs_per_item = max(5, min(120, secs_per_item))

    cmd = [
        sys.executable, "-m", "scripts.generate_daily_challenges",
        "--game", game,
        "--difficulty", difficulty,
        "--num-questions", str(num_questions),
        "--secs-per-item", str(secs_per_item),
    ]
    if countdown != "1":
        cmd.append("--no-countdown")
    if no_overwrite:
        cmd.append("--no-overwrite")

    if mode == "dates" and dates.strip():
        cmd += ["--dates", dates.strip()]
    else:
        if not start:
            start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        days = max(1, min(365, days))
        cmd += ["--start", start, "--days", str(days)]

    try:
        subprocess.Popen(cmd)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return RedirectResponse("/admin/daily", status_code=303)


@router.get("/daily/preview/{date_str}")
async def admin_daily_preview(request: Request, date_str: str):
    _require_auth(request)
    data = _get_challenge_json_s3(date_str)
    if not data:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return JSONResponse(content=data)


# ── Dataset Configuration ────────────────────────────────────────────────────

@router.get("/dataset-config", response_class=HTMLResponse)
async def admin_dataset_config(request: Request, saved: str = ""):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=303)
    lang = get_lang(request)

    svc = get_dataset_config_service()
    datasets = svc.get_all_datasets()
    games = svc.get_games()
    last_updated = svc.get_last_updated()

    return templates.TemplateResponse("admin/dataset_config.html", {
        "request": request, "lang": lang, "section": "dataset-config",
        "datasets": datasets,
        "games": games,
        "last_updated": last_updated,
        "saved": saved == "1",
    })


@router.post("/dataset-config/update-state")
async def admin_update_dataset_state(request: Request):
    _require_auth(request)
    svc = get_dataset_config_service()
    summary = svc.update_existence_state()
    return JSONResponse(content=summary)


@router.post("/dataset-config/{dataset_id}/visibility")
async def admin_toggle_dataset_visibility(request: Request, dataset_id: str):
    _require_auth(request)
    form = await request.form()
    visible = form.get("visible") == "1"
    svc = get_dataset_config_service()
    svc.toggle_visibility(dataset_id, visible)
    return RedirectResponse("/admin/dataset-config?saved=1", status_code=303)


@router.post("/dataset-config/{dataset_id}/game/{game_id}/visibility")
async def admin_toggle_game_visibility(request: Request, dataset_id: str, game_id: str):
    _require_auth(request)
    form = await request.form()
    visible = form.get("visible") == "1"
    svc = get_dataset_config_service()
    svc.toggle_game_visibility(dataset_id, game_id, visible)
    return JSONResponse(content={"success": True, "visible": visible})


@router.get("/api/datasets-config")
async def api_get_datasets_config(request: Request):
    """API endpoint to get visible datasets for frontend."""
    svc = get_dataset_config_service()
    visible = svc.get_visible_datasets()
    all_datasets = svc.get_all_datasets()
    return JSONResponse(content={
        "visible": visible,
        "datasets": {k: {"label_es": v.get("label_es"), "label_en": v.get("label_en"), "visible": v.get("visible"), "exists": v.get("exists")} for k, v in all_datasets.items()}
    })
