"""FastAPI dependencies and middleware for authentication."""

import logging
from http.cookies import SimpleCookie
from typing import Optional

from fastapi import Cookie, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from services.auth import create_access_token, decode_token
from services.users import get_user_by_id

log = logging.getLogger(__name__)


# ── Token refresh middleware ─────────────────────────────────────────────────

class TokenRefreshMiddleware(BaseHTTPMiddleware):
    """Transparently refresh the access_token cookie when it has expired
    but a valid refresh_token is still present.

    This runs on every request.  When the access token is missing/expired
    and the refresh token is valid, a fresh access token is generated and
    set as a cookie on the response.  The request itself also gets the new
    cookie injected so downstream dependencies see the user as logged-in.
    """

    async def dispatch(self, request: Request, call_next):
        access = request.cookies.get("access_token")
        refresh = request.cookies.get("refresh_token")

        new_access: str | None = None

        if not access and refresh:
            # Access token missing/expired, try refresh
            payload = decode_token(refresh)
            if payload and payload.get("type") == "refresh":
                user_id = payload.get("sub")
                user = get_user_by_id(user_id) if user_id else None
                if user and user.get("status") == "active":
                    new_access = create_access_token(user_id)
                    # Inject into request so get_current_user sees it
                    request._cookies["access_token"] = new_access
        elif access:
            # Access token present but maybe expired
            payload = decode_token(access)
            if payload is None and refresh:
                ref_payload = decode_token(refresh)
                if ref_payload and ref_payload.get("type") == "refresh":
                    user_id = ref_payload.get("sub")
                    user = get_user_by_id(user_id) if user_id else None
                    if user and user.get("status") == "active":
                        new_access = create_access_token(user_id)
                        request._cookies["access_token"] = new_access

        response = await call_next(request)

        # Set the refreshed access token cookie on the response
        if new_access:
            from core.config import get_settings
            settings = get_settings()
            response.set_cookie(
                "access_token", new_access,
                httponly=True, samesite="lax",
                max_age=settings.jwt_access_token_expire_minutes * 60,
            )
            # Also extend the refresh token cookie lifetime
            if refresh:
                response.set_cookie(
                    "refresh_token", refresh,
                    httponly=True, samesite="lax",
                    max_age=settings.jwt_refresh_token_expire_days * 86400,
                )

        return response


def _user_from_token(token: Optional[str]) -> Optional[dict]:
    """Resolve a JWT access token to a user dict (or None)."""
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user = get_user_by_id(payload["sub"])
    if not user or user.get("status") != "active":
        return None
    return user


async def get_current_user(access_token: Optional[str] = Cookie(None)) -> dict:
    """Require an authenticated user (redirects to /login otherwise)."""
    user = _user_from_token(access_token)
    if user is None:
        from fastapi.responses import RedirectResponse
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return user


async def get_optional_user(access_token: Optional[str] = Cookie(None)) -> Optional[dict]:
    """Return the current user if logged in, otherwise None."""
    return _user_from_token(access_token)
