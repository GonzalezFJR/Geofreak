"""FastAPI dependencies for authentication."""

from typing import Optional

from fastapi import Cookie, HTTPException, status

from services.auth import decode_token
from services.users import get_user_by_id


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
