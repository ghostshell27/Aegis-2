"""FastAPI assembly point.

Creates the app, runs migrations on startup, mounts the API routers, and
serves the compiled React frontend from ``static/``. Any unknown non-API
GET is rewritten to ``/index.html`` so client-side routing works.
"""
from __future__ import annotations

import os
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.database import db
from backend.services import user_profile
from backend.routes import (
    config_routes,
    curriculum_routes,
    session_routes,
    progress_routes,
    ai_routes,
)


def _static_dir() -> Path | None:
    env = os.environ.get("MATHCORE_STATIC_DIR")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.append(base / "static")
        candidates.append(Path(sys.executable).resolve().parent / "static")
    candidates.append(Path(__file__).resolve().parent.parent / "static")
    for c in candidates:
        if c.exists() and (c / "index.html").exists():
            return c
    return None


def _is_safe_subpath(base: Path, candidate: Path) -> bool:
    """Return True iff ``candidate`` resolves inside ``base`` (no traversal)."""
    try:
        base_r = base.resolve()
        cand_r = candidate.resolve()
        return cand_r == base_r or base_r in cand_r.parents
    except (OSError, RuntimeError):
        return False


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await db.run_migrations()
    await user_profile.ensure_profile()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Aegis 2", version="1.0.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        # Anchored so `http://127.0.0.1.evil.com` cannot prefix-match.
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    app.include_router(config_routes.router)
    app.include_router(curriculum_routes.router)
    app.include_router(session_routes.router)
    app.include_router(progress_routes.router)
    app.include_router(ai_routes.router)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True}

    static = _static_dir()
    if static is not None:
        assets_dir = static / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        index_file = static / "index.html"

        # `response_model=None` tells FastAPI not to derive a Pydantic response
        # model from the return type. Without it, FastAPI raises
        # `FastAPIError: Invalid args for response field! ...` on routes that
        # return Response subclasses (FileResponse / JSONResponse), since
        # Response is not a Pydantic-compatible type.
        @app.get("/", response_model=None)
        async def root():
            return FileResponse(str(index_file))

        @app.get("/{path:path}", response_model=None)
        async def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"error": "not_found"}, status_code=404)
            target = static / path
            if _is_safe_subpath(static, target) and target.is_file():
                return FileResponse(str(target))
            return FileResponse(str(index_file))
    else:
        @app.get("/")
        async def placeholder() -> dict:
            return {
                "ok": True,
                "note": (
                    "Frontend assets not built yet. Run `npm run build` inside "
                    "`frontend/` or `build.bat` from the project root."
                ),
            }

    return app


app = create_app()
