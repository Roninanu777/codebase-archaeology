from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def require_synthesis_token(
    x_archaeology_token: str | None = Header(default=None),
) -> None:
    expected = os.environ.get("SYNTHESIS_TOKEN", "").strip()
    if not expected:
        return
    if not x_archaeology_token or not secrets.compare_digest(x_archaeology_token, expected):
        raise HTTPException(
            status_code=403,
            detail="invalid or missing X-Archaeology-Token",
        )
