# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Aegis 2.

Bundles the Python launcher, FastAPI backend modules, and the compiled
Vite frontend (in ``static/``) into a single Windows .exe located at
``dist/Aegis2/Aegis2.exe``. The ``data/`` folder is copied alongside
by the build script so the launcher can write ``userdata.db`` next to it.
"""
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH).resolve()

datas = []

static_dir = ROOT / "static"
if static_dir.exists():
    datas.append((str(static_dir), "static"))

curriculum = ROOT / "data" / "curriculum.json"
if curriculum.exists():
    datas.append((str(curriculum), "data"))

# PyInstaller bundles .py modules automatically but NOT .sql files in the
# migrations directory. Without this entry, run_migrations() finds zero
# files and the first query fails with "no such table". Ship the whole
# migrations folder explicitly.
migrations_dir_src = ROOT / "backend" / "migrations"
if migrations_dir_src.exists():
    datas.append((str(migrations_dir_src), "backend/migrations"))

hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "h11",
    "httptools",
    "websockets",
    "aiosqlite",
    "cryptography",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "cryptography.hazmat.primitives.ciphers.aead",
    "httpx",
    "httpcore",
    "anyio",
    "anyio._backends._asyncio",
    "sniffio",
    "pydantic",
    "pydantic_core",
    "pydantic.deprecated.decorator",
    "fastapi",
    "starlette",
    "starlette.middleware.cors",
    "starlette.middleware.errors",
    "starlette.middleware.exceptions",
    "starlette.routing",
    "backend",
    "backend.main",
    "backend.database",
    "backend.crypto",
    "backend.ai_wrapper",
    "backend.models",
    "backend.routes",
    "backend.routes.config_routes",
    "backend.routes.curriculum_routes",
    "backend.routes.session_routes",
    "backend.routes.progress_routes",
    "backend.routes.ai_routes",
    "backend.services",
    "backend.services.user_profile",
    "backend.services.session_service",
    "backend.services.curriculum_service",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Aegis2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Aegis2",
)
