"""Сквозной сценарий: регистрация -> подтверждение -> вход -> создание книги
-> загрузка словаря -> он виден в списке и скачивается."""

import re

import pytest
from fastapi.testclient import TestClient

from app.email_sender import ConsoleEmailSender
from app.main import app

_last_code = {}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _capture_send_code(self, to_email, code):
    _last_code[to_email] = code


@pytest.fixture(autouse=True)
def patch_email(monkeypatch):
    monkeypatch.setattr(ConsoleEmailSender, "send_code", _capture_send_code)


def test_full_flow(client):
    email = "reader@example.com"

    resp = client.post(
        "/api/auth/register",
        data={"login": "reader1", "email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    code = _last_code[email]
    assert re.fullmatch(r"\d{6}", code)

    resp = client.post("/api/auth/verify", data={"email": email, "code": code}, follow_redirects=False)
    assert resp.status_code == 303

    resp = client.post(
        "/api/auth/login",
        data={"login_or_email": "reader1", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "session" in resp.cookies

    resp = client.post(
        "/api/books",
        data={"title": "Test Book", "author": "Jane Doe", "series_name": "", "series_index": ""},
    )
    assert resp.status_code == 200
    book_id = resp.json()["id"]

    dic_content = b"Hello = \xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82, GREETING, it, note\n"
    resp = client.post(
        "/api/dictionaries",
        data={"book_id": book_id, "source_lang": "en", "target_lang": "ru", "description": "test"},
        files={"file": ("test.dic", dic_content, "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    dict_id = resp.json()["id"]
    assert resp.json()["entries_count"] == 1

    resp = client.get("/api/dictionaries", params={"source_lang": "en", "target_lang": "ru"})
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert dict_id in ids

    resp = client.get(f"/api/dictionaries/{dict_id}/download")
    assert resp.status_code == 200
    assert resp.content == dic_content


def test_upload_rejects_bad_format_without_auth(client):
    resp = client.post(
        "/api/dictionaries",
        data={"book_id": "nonexistent", "source_lang": "en", "target_lang": "ru"},
        files={"file": ("test.dic", "Hello = Привет\n".encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 401


def test_index_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Словари" in resp.text
