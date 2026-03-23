"""
GeoFreak — Entry point.
Run locally:   python main.py
Docker build:  python main.py --docker [--force-recreate]
"""

import argparse
import os
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

from core.config import get_settings  # noqa: E402


def create_app():
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.sessions import SessionMiddleware

    from routers import pages, api, games, admin, auth, social, duels, tournaments

    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Plataforma de juegos y exploración geográfica",
        version="0.1.0",
    )

    # Session middleware (for admin auth)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
    )

    # Static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Routers
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(api.router, prefix="/api")
    app.include_router(games.router)
    app.include_router(social.router)
    app.include_router(duels.router)
    app.include_router(tournaments.router)
    app.include_router(admin.router)

    # Custom 404 handler
    from fastapi import Request
    from core.i18n import get_lang
    from core.templates import templates as tpl

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        lang = get_lang(request)
        user = None
        try:
            token = request.cookies.get("access_token")
            if token:
                from core.auth import _user_from_token
                user = _user_from_token(token)
        except Exception:
            pass
        return tpl.TemplateResponse(
            "404.html", {"request": request, "lang": lang, "user": user},
            status_code=404,
        )

    # Flush analytics buffer on shutdown
    from contextlib import asynccontextmanager
    from services.analytics import flush as flush_analytics

    @asynccontextmanager
    async def lifespan(app):
        yield
        flush_analytics()

    app.router.lifespan_context = lifespan

    return app


app = create_app()


def run_docker(force_recreate: bool = False):
    """Build and run with docker compose."""
    cmd = ["docker", "compose", "up", "--build", "-d"]
    if force_recreate:
        cmd.append("--force-recreate")
    print(f"🐳 Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def run_local():
    """Run locally with uvicorn."""
    import uvicorn

    settings = get_settings()
    print(f"🌍 GeoFreak running at http://{settings.app_host}:{settings.app_port}")
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=settings.app_debug)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GeoFreak launcher")
    parser.add_argument("--docker", action="store_true", help="Deploy with Docker")
    parser.add_argument(
        "--force-recreate",
        action="store_true",
        help="Force recreate Docker containers",
    )
    args = parser.parse_args()

    if args.docker:
        run_docker(args.force_recreate)
    else:
        run_local()
