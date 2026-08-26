from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request

from app.db import get_conn


def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session")
    if not token:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT users.* FROM sessions "
            "JOIN users ON users.id = sessions.user_id "
            "WHERE sessions.token = ? AND sessions.expires_at > ?",
            (token, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    return dict(row) if row else None


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    return user


def require_verified_user(request: Request) -> dict:
    user = require_user(request)
    if not user["email_verified_at"]:
        raise HTTPException(status_code=403, detail="Email не подтверждён")
    return user
