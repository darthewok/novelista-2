from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .routers import books, seed, stream, uploads, foundation, outline, chapters, settings as settings_router


FRONTEND_DIST = Path(
    os.environ.get("NOVELISTA_FRONTEND_DIST")
    or Path(__file__).resolve().parents[2] / "frontend" / "dist"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Novelista", version="0.1.0", lifespan=lifespan)

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


HAS_FRONTEND = (FRONTEND_DIST / "index.html").is_file()

if HAS_FRONTEND and (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


# Registered last so API routes win. Serves built files or the SPA index.
@app.get("/{full_path:path}")
def frontend(full_path: str):
    if full_path == "api" or full_path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if not HAS_FRONTEND:
        if full_path == "":
            return PlainTextResponse(
                "Novelista backend is running. The frontend build (frontend/dist) is missing."
            )
        return PlainTextResponse("Not Found", status_code=404)
    root = FRONTEND_DIST.resolve()
    candidate = (root / full_path).resolve()
    if candidate.is_file() and candidate.is_relative_to(root):
        return FileResponse(candidate)
    return FileResponse(root / "index.html")
