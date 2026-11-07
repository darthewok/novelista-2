from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from . import jobs
from .routers import books, seed, stream, uploads, foundation, outline, chapters, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    jobs.recover_orphans()
    yield


app = FastAPI(title="Novelista", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books.router)
app.include_router(seed.router)
app.include_router(uploads.router)
app.include_router(outline.router)
app.include_router(chapters.router)
app.include_router(foundation.router)
app.include_router(stream.router)
app.include_router(settings_router.router)


@app.get("/api/health")
def health():
    return {"ok": True}
