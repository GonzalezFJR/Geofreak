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


def create_app():
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.sessions import SessionMiddleware

    from routers import pages, api, games, admin

    app = FastAPI(
        title=os.getenv("APP_NAME", "GeoFreak"),
        description="Plataforma de juegos y exploración geográfica",
        version="0.1.0",
    )

    # Session middleware (for admin auth)
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("SECRET_KEY", "geofreak-dev-secret-change-me"),
    )

    # Static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Routers
    app.include_router(pages.router)
    app.include_router(api.router, prefix="/api")
    app.include_router(games.router)
    app.include_router(admin.router)

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

    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", 8000))
    debug = os.getenv("APP_DEBUG", "true").lower() == "true"
    print(f"🌍 GeoFreak running at http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=debug)


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
