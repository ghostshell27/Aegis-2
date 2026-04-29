"""/api/config -- AI provider configuration (read, write, test, export, import)."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend import crypto, ai_wrapper
from backend.database import db, db_path
from backend.models import ConfigPayload, ConfigView


router = APIRouter(prefix="/api/config", tags=["config"])


def _preview(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "..." + key[-4:]


@router.get("", response_model=ConfigView)
async def get_config() -> ConfigView:
    row = await db.fetch_one(
        "SELECT api_key_ciphertext, base_url, model_name, custom_system_prompt, "
        "provider_hint FROM app_config WHERE id = 1"
    )
    if not row:
        return ConfigView(
            configured=False,
            base_url="https://api.anthropic.com",
            model_name="",
            custom_system_prompt="",
            provider_hint="auto",
            api_key_preview="",
        )
    api_key = crypto.decrypt(row["api_key_ciphertext"])
    return ConfigView(
        configured=bool(api_key),
        base_url=row["base_url"],
        model_name=row["model_name"],
        custom_system_prompt=row["custom_system_prompt"] or "",
        provider_hint=row["provider_hint"] or "auto",
        api_key_preview=_preview(api_key),
    )


@router.post("")
async def save_config(payload: ConfigPayload) -> dict:
    existing = await db.fetch_one(
        "SELECT api_key_ciphertext FROM app_config WHERE id = 1"
    )
    new_key = (payload.api_key or "").strip()
    if new_key:
        # HTTP headers (Authorization / x-api-key) must be ASCII. Reject keys
        # containing smart quotes, accented characters, em-dashes, non-breaking
        # spaces, etc., before they trigger an opaque UnicodeEncodeError on
        # the first request. This is almost always the fault of pasting from
        # a rich-text source.
        try:
            new_key.encode("ascii")
        except UnicodeEncodeError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "API key contains non-ASCII characters. Re-copy it from "
                    "the provider's dashboard (avoid rich-text editors and "
                    "messaging apps that auto-format text) and try again."
                ),
            )
        ciphertext = crypto.encrypt(new_key)
    elif existing:
        ciphertext = existing["api_key_ciphertext"]
    else:
        raise HTTPException(
            status_code=400,
            detail="API key is required on first setup.",
        )
    await db.execute(
        "INSERT INTO app_config(id, api_key_ciphertext, base_url, model_name, "
        "custom_system_prompt, provider_hint, updated_at) "
        "VALUES (1, ?, ?, ?, ?, ?, datetime('now')) "
        "ON CONFLICT(id) DO UPDATE SET "
        "api_key_ciphertext = excluded.api_key_ciphertext, "
        "base_url = excluded.base_url, model_name = excluded.model_name, "
        "custom_system_prompt = excluded.custom_system_prompt, "
        "provider_hint = excluded.provider_hint, updated_at = datetime('now')",
        (
            ciphertext,
            payload.base_url.rstrip("/"),
            payload.model_name,
            payload.custom_system_prompt or "",
            payload.provider_hint,
        ),
    )
    return {"ok": True}


@router.post("/test")
async def test_config() -> dict:
    try:
        text = await ai_wrapper.chat(
            system_prompt="You are a health-check responder.",
            messages=[
                {
                    "role": "user",
                    "content": "Reply with only the word OK.",
                }
            ],
            max_tokens=16,
            temperature=0.0,
        )
    except ai_wrapper.AIProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "reply": text.strip()[:64]}


@router.delete("")
async def clear_config() -> dict:
    await db.execute("DELETE FROM app_config WHERE id = 1")
    return {"ok": True}


_SQLITE_MAGIC = b"SQLite format 3\x00"
_EXPECTED_TABLES = frozenset({
    "app_config", "user_profile", "topic_progress",
    "sessions", "messages", "exercise_attempts",
    "capstone_progress", "domain_stats",
})


@router.get("/export")
async def export_progress() -> FileResponse:
    """Stream a consistent snapshot of ``userdata.db`` as a download.

    Uses SQLite's online-backup API so the snapshot is consistent even if
    a query happens to be in flight on another aiosqlite connection.
    """
    src = db_path()
    if not src.exists():
        raise HTTPException(status_code=404, detail="No saved data yet.")

    fd, tmp_path = tempfile.mkstemp(prefix="aegis2_export_", suffix=".db")
    os.close(fd)

    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(tmp_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()

    today = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"aegis2-progress-{today}.db"

    def _cleanup() -> None:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return FileResponse(
        tmp_path,
        media_type="application/octet-stream",
        filename=filename,
        background=BackgroundTask(_cleanup),
    )


@router.post("/import")
async def import_progress(file: UploadFile = File(...)) -> dict:
    """Replace ``userdata.db`` with the uploaded backup.

    Workflow:
      1. Validate the upload starts with the SQLite magic header.
      2. Open it in a sandbox temp file and confirm at least one of our
         tables exists (so a random SQLite file from elsewhere can't
         silently overwrite progress).
      3. Move the current DB aside as ``userdata.db.bak`` (preserved for
         recovery if the new one turns out to be bad).
      4. Atomically rename the temp file over the live DB.
      5. Run migrations to upgrade any older schema to the current one.
    """
    content = await file.read()
    if len(content) < 100 or not content.startswith(_SQLITE_MAGIC):
        raise HTTPException(
            status_code=400,
            detail="That file does not look like a SQLite database backup.",
        )

    target = db_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix="aegis2_import_", suffix=".db", dir=str(target.parent)
    )
    os.close(fd)
    Path(tmp_path).write_bytes(content)

    test_conn = sqlite3.connect(tmp_path)
    try:
        rows = test_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        tables = {r[0] for r in rows}
    except sqlite3.DatabaseError as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=400, detail=f"Backup is corrupted: {e}"
        )
    finally:
        test_conn.close()

    if not (tables & _EXPECTED_TABLES):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=400,
            detail=(
                "This SQLite file does not look like an Aegis 2 progress backup."
            ),
        )

    # Save the current DB as a recovery copy, then atomically swap in the new one.
    backup = target.with_suffix(target.suffix + ".bak")
    if target.exists():
        if backup.exists():
            try:
                backup.unlink()
            except OSError:
                pass
        try:
            os.replace(target, backup)
        except OSError:
            pass

    os.replace(tmp_path, target)

    # Bring the imported DB up to the current schema version.
    await db.run_migrations()

    return {
        "ok": True,
        "tables_found": sorted(tables),
        "backup_kept_at": str(backup) if backup.exists() else None,
    }
