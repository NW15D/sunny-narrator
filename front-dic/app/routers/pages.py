from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates

from app.constants import LANG_CODES
from app.deps import get_current_user
from app.routers.dictionaries_api import list_dictionaries

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
router = APIRouter()


@router.get("/")
def index(
    request: Request,
    source_lang: str = Query(""),
    target_lang: str = Query(""),
    author: str = Query(""),
    series_name: str = Query(""),
    q: str = Query(""),
):
    result = list_dictionaries(
        source_lang=source_lang,
        target_lang=target_lang,
        author=author,
        uploader="",
        series_name=series_name,
        book_id="",
        q=q,
        page=1,
        page_size=50,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "items": result["items"],
            "lang_codes": LANG_CODES,
            "user": get_current_user(request),
            "filters": {
                "source_lang": source_lang,
                "target_lang": target_lang,
                "author": author,
                "series_name": series_name,
                "q": q,
            },
        },
    )


@router.get("/upload")
def upload_page(request: Request):
    return templates.TemplateResponse(
        request,
        "upload.html",
        {"lang_codes": LANG_CODES, "user": get_current_user(request)},
    )


@router.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"user": get_current_user(request)})


@router.get("/verify")
def verify_page(request: Request, email: str = Query("")):
    return templates.TemplateResponse(
        request, "verify.html", {"email": email, "user": get_current_user(request)}
    )


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user": get_current_user(request)})
