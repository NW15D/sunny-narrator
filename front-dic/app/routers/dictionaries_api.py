import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.config import config
from app.constants import LANG_CODES
from app.db import get_conn
from app.deps import require_verified_user
from app.dic_validator import validate_dic_content

router = APIRouter(prefix="/api/dictionaries", tags=["dictionaries"])


@router.get("")
def list_dictionaries(
    source_lang: str = Query(""),
    target_lang: str = Query(""),
    author: str = Query(""),
    uploader: str = Query(""),
    series_name: str = Query(""),
    book_id: str = Query(""),
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions = ["df.status = 'approved'"]
    params: list = []
    if source_lang:
        conditions.append("df.source_lang = ?")
        params.append(source_lang)
    if target_lang:
        conditions.append("df.target_lang = ?")
        params.append(target_lang)
    if author:
        conditions.append("b.author LIKE ?")
        params.append(f"%{author}%")
    if uploader:
        conditions.append("u.login LIKE ?")
        params.append(f"%{uploader}%")
    if series_name:
        conditions.append("b.series_name LIKE ?")
        params.append(f"%{series_name}%")
    if book_id:
        conditions.append("df.book_id = ?")
        params.append(book_id)
    if q:
        conditions.append("b.title LIKE ?")
        params.append(f"%{q}%")

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT df.id, df.source_lang, df.target_lang, df.original_filename,
                   df.file_size_bytes, df.entries_count, df.description,
                   df.downloads_count, df.uploaded_at,
                   b.id AS book_id, b.title AS book_title, b.author AS book_author,
                   b.series_name, b.series_index,
                   u.login AS uploader_login
            FROM dictionary_files df
            JOIN books b ON b.id = df.book_id
            JOIN users u ON u.id = df.uploader_id
            WHERE {where}
            ORDER BY df.uploaded_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, offset),
        ).fetchall()
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM dictionary_files df
            JOIN books b ON b.id = df.book_id
            JOIN users u ON u.id = df.uploader_id
            WHERE {where}
            """,
            params,
        ).fetchone()["c"]

    return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/{dictionary_id}")
def get_dictionary(dictionary_id: str):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT df.*, b.title AS book_title, b.author AS book_author,
                   b.series_name, b.series_index, u.login AS uploader_login
            FROM dictionary_files df
            JOIN books b ON b.id = df.book_id
            JOIN users u ON u.id = df.uploader_id
            WHERE df.id = ?
            """,
            (dictionary_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Словарь не найден")
    return dict(row)


@router.get("/{dictionary_id}/download")
def download_dictionary(dictionary_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM dictionary_files WHERE id = ?", (dictionary_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Словарь не найден")
        conn.execute(
            "UPDATE dictionary_files SET downloads_count = downloads_count + 1 WHERE id = ?",
            (dictionary_id,),
        )

    path = Path(row["storage_path"])
    if not path.exists():
        raise HTTPException(410, "Файл отсутствует на диске")
    return FileResponse(path, filename=row["original_filename"], media_type="text/plain")


@router.post("")
async def upload_dictionary(
    file: UploadFile = File(...),
    book_id: str = Form(...),
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    description: str = Form(""),
    user=Depends(require_verified_user),
):
    safe_name = Path(file.filename or "").name
    if not safe_name.lower().endswith(".dic"):
        raise HTTPException(400, "Разрешены только файлы с расширением .dic")
    if source_lang not in LANG_CODES or target_lang not in LANG_CODES:
        raise HTTPException(400, "Неизвестный код языка")

    raw = await file.read()
    if len(raw) < config.min_file_size_bytes:
        raise HTTPException(400, "Файл пустой или слишком мал")
    if len(raw) > config.max_file_size_bytes:
        limit_mb = config.max_file_size_bytes // (1024 * 1024)
        raise HTTPException(400, f"Файл превышает максимальный размер {limit_mb} МБ")
    if b"\x00" in raw:
        raise HTTPException(400, "Файл не является текстовым (обнаружены нулевые байты)")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Файл должен быть в кодировке UTF-8")

    errors, entries_count = validate_dic_content(text)
    if errors:
        raise HTTPException(400, {"errors": errors})

    with get_conn() as conn:
        book = conn.execute("SELECT id FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            raise HTTPException(400, "Указанная книга не найдена")

        dictionary_id = str(uuid.uuid4())
        dest_dir = config.uploads_dir / dictionary_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / safe_name
        dest_path.write_bytes(raw)

        conn.execute(
            """
            INSERT INTO dictionary_files
                (id, book_id, uploader_id, source_lang, target_lang, original_filename,
                 storage_path, file_size_bytes, entries_count, description,
                 downloads_count, status, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'approved', ?)
            """,
            (
                dictionary_id,
                book_id,
                user["id"],
                source_lang,
                target_lang,
                safe_name,
                str(dest_path),
                len(raw),
                entries_count,
                description.strip() or None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    return {"id": dictionary_id, "entries_count": entries_count}
