"""SQLite database access with a tiny forward-only migration runner.

All data lives in ``{MATHCORE_DATA_DIR}/userdata.db``. Migrations are plain
``.sql`` files in ``backend/migrations``, executed in filename order. A
``schema_migrations`` table records applied files so reruns are no-ops.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Any


def data_dir() -> Path:
    value = os.environ.get("MATHCORE_DATA_DIR")
    if value:
        path = Path(value)
    else:
        path = Path(__file__).resolve().parent.parent / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "userdata.db"


def migrations_dir() -> Path:
    """Locate migration SQL files whether running from source or frozen."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.append(base / "backend" / "migrations")
    candidates.append(Path(__file__).resolve().parent / "migrations")
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


class Database:
    def __init__(self) -> None:
        self._path = db_path()

    @asynccontextmanager
    async def connect(self):
        """Open a fresh connection, configure pragmas, and close on exit."""
        conn = await aiosqlite.connect(self._path)
        try:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON")
            # Stay in the default rollback journal mode. WAL caused frozen-bundle
            # connections to disagree about schema state on Windows + Python
            # 3.14 + aiosqlite -- separate connections in the same process saw
            # different views of the database, producing spurious
            # "no such table" errors for tables that demonstrably existed.
            await conn.execute("PRAGMA busy_timeout = 5000")
            yield conn
        finally:
            await conn.close()

    def _run_migrations_sync(self) -> None:
        """Run migrations using the stdlib sqlite3 module (synchronous).

        We deliberately avoid aiosqlite here. On Python 3.14 + aiosqlite
        0.22.1 + PyInstaller frozen bundles, schema changes committed by the
        migration thread were not visible to subsequent aiosqlite connection
        threads in the same process -- ``sqlite_master`` reported the new
        tables, yet ``SELECT FROM app_config`` returned "no such table".
        Driving migrations through the stdlib in the main thread sidesteps
        that quirk completely; later request handlers (which use aiosqlite)
        then see a fully-populated schema on disk.
        """
        # Make sure the data dir exists before sqlite3 tries to create the file.
        data_dir()
        conn = sqlite3.connect(self._path, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            applied = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}

            mdir = migrations_dir()
            files = sorted(p for p in mdir.glob("*.sql") if p.is_file())
            for f in files:
                if f.name in applied:
                    continue
                sql = f.read_text(encoding="utf-8")
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations(filename) VALUES (?)",
                    (f.name,),
                )
        finally:
            conn.close()

    async def run_migrations(self) -> None:
        import asyncio
        # Run in a worker thread so we don't block the event loop, but stay
        # outside aiosqlite's threading model.
        await asyncio.to_thread(self._run_migrations_sync)

    async def fetch_one(self, query: str, params: tuple[Any, ...] = ()) -> dict | None:
        async with self.connect() as conn:
            async with conn.execute(query, params) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def fetch_all(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> list[dict]:
        async with self.connect() as conn:
            async with conn.execute(query, params) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def execute(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> int:
        async with self.connect() as conn:
            async with conn.execute(query, params) as cur:
                await conn.commit()
                return cur.lastrowid or 0

    async def execute_many(
        self, query: str, params_list: list[tuple[Any, ...]]
    ) -> None:
        async with self.connect() as conn:
            await conn.executemany(query, params_list)
            await conn.commit()


db = Database()


async def iter_messages(session_id: int) -> AsyncIterator[dict]:
    async with db.connect() as conn:
        async with conn.execute(
            "SELECT id, role, content, created_at, meta FROM messages "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cur:
            async for row in cur:
                yield dict(row)
