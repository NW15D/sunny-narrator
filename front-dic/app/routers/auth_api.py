import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.config import config
from app.db import get_conn
from app.email_sender import get_email_sender
from app.security import generate_code, generate_session_token, hash_code, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _issue_code(conn, user_id: str, purpose: str) -> None:
    code = generate_code()
    conn.execute(
        "INSERT INTO email_verifications (id, user_id, code_hash, purpose, expires_at, attempts, created_at) "
        "VALUES (?, ?, ?, ?, ?, 0, ?)",
        (
            str(uuid.uuid4()),
            user_id,
            hash_code(code),
            purpose,
            (_now() + timedelta(minutes=config.code_ttl_minutes)).isoformat(),
            _now().isoformat(),
        ),
    )
    row = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    get_email_sender().send_code(row["email"], code)


@router.post("/register")
def register(login: str = Form(...), email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    login = login.strip()
    if len(password) < 8:
        raise HTTPException(400, "Пароль должен быть не короче 8 символов")
    if not login or not email:
        raise HTTPException(400, "Логин и email обязательны")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? OR login = ?", (email, login)
        ).fetchone()
        if existing:
            raise HTTPException(409, "Логин или email уже заняты")

        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, login, email, password_hash, email_verified_at, created_at) "
            "VALUES (?, ?, ?, ?, NULL, ?)",
            (user_id, login, email, hash_password(password), _now().isoformat()),
        )
        _issue_code(conn, user_id, "register")

    return RedirectResponse(url=f"/verify?email={email}", status_code=303)


@router.post("/verify")
def verify(email: str = Form(...), code: str = Form(...)):
    email = email.strip().lower()
    with get_conn() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            raise HTTPException(404, "Пользователь не найден")

        v = conn.execute(
            "SELECT * FROM email_verifications WHERE user_id = ? AND purpose = 'register' "
            "ORDER BY created_at DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if not v:
            raise HTTPException(400, "Код не запрошен")
        if v["attempts"] >= config.code_max_attempts:
            raise HTTPException(429, "Превышено число попыток, запросите код заново")
        if datetime.fromisoformat(v["expires_at"]) < _now():
            raise HTTPException(400, "Код истёк")

        conn.execute("UPDATE email_verifications SET attempts = attempts + 1 WHERE id = ?", (v["id"],))
        if hash_code(code) != v["code_hash"]:
            raise HTTPException(400, "Неверный код")

        conn.execute(
            "UPDATE users SET email_verified_at = ? WHERE id = ?",
            (_now().isoformat(), user["id"]),
        )

    return RedirectResponse(url="/login", status_code=303)


@router.post("/login")
def login(login_or_email: str = Form(...), password: str = Form(...)):
    identifier = login_or_email.strip().lower()
    with get_conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE lower(login) = ? OR lower(email) = ?",
            (identifier, identifier),
        ).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise HTTPException(401, "Неверный логин/email или пароль")

        token = generate_session_token()
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (token, user["id"], (_now() + timedelta(days=30)).isoformat(), _now().isoformat()),
        )

    redirect = RedirectResponse(url="/", status_code=303)
    redirect.set_cookie(
        "session", token, httponly=True, samesite="lax", max_age=30 * 24 * 3600
    )
    return redirect


@router.post("/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        with get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    redirect = RedirectResponse(url="/", status_code=303)
    redirect.delete_cookie("session")
    return redirect
