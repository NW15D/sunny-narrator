import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Query

from app.db import get_conn
from app.deps import require_verified_user

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("")
def list_books(q: str = Query("", max_length=200)):
    like = f"%{q.strip()}%"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY title LIMIT 20",
            (like, like),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("")
def create_book(
    title: str = Form(...),
    author: str = Form(...),
    series_name: str = Form(""),
    series_index: str = Form(""),
    user=Depends(require_verified_user),
):
    with get_conn() as conn:
        book_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO books (id, title, author, series_name, series_index, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                book_id,
                title.strip(),
                author.strip(),
                series_name.strip() or None,
                int(series_index) if series_index.strip().isdigit() else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return {"id": book_id}
