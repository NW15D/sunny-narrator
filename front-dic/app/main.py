import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.routers import auth_api, books_api, dictionaries_api, pages

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Sunny Narrator Dictionary Hub", lifespan=lifespan)

app.include_router(pages.router)
app.include_router(auth_api.router)
app.include_router(books_api.router)
app.include_router(dictionaries_api.router)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
