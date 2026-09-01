from __future__ import annotations

import secrets

from fastapi import Header

from app.config import settings
from app.errors import NotLoggedInError


async def require_token(
    x_api_token: str | None = Header(default=None, alias="X-API-Token"),
) -> None:
    if settings.api_token and not secrets.compare_digest(
        settings.api_token,
        x_api_token or "",
    ):
        raise NotLoggedInError(msg="invalid or missing API token")
