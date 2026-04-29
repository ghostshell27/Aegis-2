# Aegis 2

> A portable, self-contained desktop AI tutor for **Algebra** and **Calculus**.
> Bring your own API key (Anthropic, OpenAI, OpenRouter, Chutes, or any
> OpenAI-compatible endpoint), drop the folder on a USB stick, and study
> anywhere — no installer, no registry writes, no network access except to
> the AI provider you choose.

Aegis 2 teaches each topic through a real-world hook scenario, a short
explanation, a worked example, and progressively harder exercises. When
you answer wrong, the AI does **not** say "try again" — it narrates the
real-world consequence of your mistake using your wrong numbers, then
walks you back through the reasoning. Click **I don't know** at any point
(or just type *"no sé"* / *"I don't know"*) and it switches into pure
Socratic mode.

---

## Features

- **Two complete tracks** — 10 units of Algebra + 10 units of Calculus,
  42 topics, capped by a structural-engineering / business-modelling
  capstone for each track.
- **Adaptive learning** — per-topic mastery score, attempt counts,
  per-error-tag pattern tracking, and preferred real-world domain
  (structural engineering, game development, personal finance,
  epidemiology, architecture, computer graphics, sports analytics).
- **LaTeX-rendered math** — KaTeX renders every formula; the AI is told
  to write `$inline$` and `$$display$$` math, and the parser repairs
  common AI escaping mistakes (`\sqrt`, `\frac`, `\beta`, etc.) on the
  way in.
- **Provider-agnostic** — Anthropic Messages API and OpenAI-compatible
  Chat Completions both supported, auto-detected from the base URL or
  set explicitly.
- **Encrypted API key at rest** — AES-GCM, key derived from the
  hostname + Windows user. Copying your USB to a different machine
  invalidates the stored key (by design) and prompts re-setup.
- **Resumable sessions** — closing the app or browser leaves your chat
  in the database. Click the topic again and you pick up exactly where
  you left off, with the suggestion chips, exercise banner, and phase
  tag re-hydrated.
- **Live context-usage bar** — shows how many tokens of the model's
  context window your conversation is consuming, color-coded green →
  amber → red.
- **One-click backup / restore** — Settings → Backup &
  restore exports a single `.db` file containing every session, every
  message, your mastery, your encrypted API key, and your capstone
  state. Import the file later (or on a different install) to
  reconstitute everything.
- **Portable build** — a single PyInstaller bundle at
  `dist\Aegis2\Aegis2.exe` plus a `data\` folder. Drop on a USB stick,
  double-click, study.

---

## Architecture

```
+-----------------------------+        +--------------------+
|  React + Vite (frontend/)   | <----> | FastAPI (backend/) |
|  served from static/        |  HTTP  |  port 8765         |
+-----------------------------+        +---------+----------+
                                                  |
                                       +----------v----------+
                                       |  aiosqlite + sqlite3|
                                       |  data/userdata.db   |
                                       +----------+----------+
                                                  |
                                       +----------v----------+
                                       | httpx -> AI provider|
                                       | (Anthropic / OpenAI)|
                                       +---------------------+
```

- **Backend** — Python 3.11+, FastAPI, aiosqlite, httpx, cryptography.
  Forward-only SQL migrations in `backend/migrations/*.sql` run at
  startup. A strict JSON envelope contract between the backend and the
  AI lets the backend update progress deterministically without ever
  scraping prose.
- **Frontend** — React 18 + Vite, react-router HashRouter, react-markdown
  with `remark-math` + `rehype-katex`. No bundler-side state; everything
  flows through `frontend/src/api.js`.
- **Launcher** — `launcher.py` finds a free port (preferred 8765),
  boots uvicorn, opens the default browser, and serves the bundled
  React app from `static/`. PyInstaller (`mathcore.spec`) packages
  everything into a single portable folder.

---

## Quick start (use the .exe)

1. Grab the latest release zip (or build from source — see below).
2. Unzip anywhere. The folder layout looks like:
   ```
   Aegis2\
     Aegis2.exe
     _internal\        ← Python runtime + bundled frontend
     data\
       curriculum.json
   ```
3. Double-click `Aegis2.exe`. A console window opens and your default
   browser launches at `http://127.0.0.1:8765`.
4. The first time, you'll be taken to **Settings**. Enter:
   - **API key** — from your AI provider's dashboard.
   - **Base URL** — defaults to `https://api.anthropic.com`. Presets
     for OpenAI, OpenRouter, Chutes, and local LM Studio are one
     click away.
   - **Model name** — e.g. `claude-opus-4-7`, `gpt-4o-mini`,
     `anthropic/claude-3.5-sonnet`.
5. Click **Test connection** to verify, then **Save**.

Close the console window to shut down the app.

---

## Build from source

**Requirements:** Python 3.11+ and Node.js 18+ on `PATH`.

```bat
build.bat
```

That single script:

1. Creates `venv\` if missing and installs `requirements.txt`.
2. Runs `npm install` + `npm run build` inside `frontend\`.
3. Copies the Vite output to `static\`.
4. Runs `python -m PyInstaller mathcore.spec`.
5. Copies `data\` and `README.txt` next to the produced `Aegis2.exe`.

Result: `dist\Aegis2\Aegis2.exe`.

The script prechecks for Python and Node, pauses on every error, and
pauses on success — so the console never closes before you can read
what happened.

### Running from source without packaging

You don't need Node.js just to test the backend. Once the venv exists:

```bat
launch_dev.bat
```

This activates the venv and runs `launcher.py`. Without a built
frontend you'll get a placeholder JSON page at `/`, but the API at
`/api/health` (and every other endpoint) works.

For full hot-reload development:

```bat
:: Terminal A — backend
venv\Scripts\activate
python launcher.py

:: Terminal B — frontend with HMR
cd frontend
npm install
npm run dev      :: opens http://127.0.0.1:5173 with /api proxied to 8765
```

---

## Updating without losing progress

Aegis 2 stores every byte of your progress in **one file**:
`data\userdata.db`.

**Recommended workflow:**

1. Open the app → Settings → **Export progress**. You get a single
   `aegis2-progress-YYYYMMDD-HHMMSS.db` file. Save it somewhere safe.
2. Replace your portable folder with the new build.
3. Open the app → Settings → **Import progress…** and pick the saved
   file. The previous DB is preserved as `userdata.db.bak` next to
   the new one in case you want to roll back.

**Or, in-place update:** copy only the new `Aegis2.exe` and `_internal\`
into your existing folder. Leave `data\` alone. Schema upgrades happen
automatically on the next launch via the migration runner.

---

## Project layout

```
Aegis 2/
├── backend/
│   ├── ai_wrapper.py          # provider-agnostic httpx client + JSON repair
│   ├── crypto.py              # machine-bound AES-GCM for the API key
│   ├── database.py            # aiosqlite wrapper, migration runner
│   ├── main.py                # FastAPI assembly, CORS, SPA fallback
│   ├── models.py              # Pydantic request/response models
│   ├── migrations/
│   │   └── 001_initial.sql    # forward-only schema
│   ├── routes/                # /api/config, /api/session, /api/progress, …
│   └── services/
│       ├── curriculum_service.py
│       ├── session_service.py # the teaching engine + JSON envelope
│       └── user_profile.py
├── frontend/
│   ├── src/
│   │   ├── api.js             # single fetch helper
│   │   ├── App.jsx            # router + brand mark
│   │   ├── components/
│   │   │   ├── ChatMessage.jsx
│   │   │   ├── ConfigScreen.jsx
│   │   │   ├── ErrorBoundary.jsx
│   │   │   ├── HomeScreen.jsx
│   │   │   ├── SessionScreen.jsx
│   │   │   └── TopicMap.jsx
│   │   └── styles/main.css
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── data/
│   └── curriculum.json        # 2 tracks · 21 units · 42 topics
├── launcher.py                # PyInstaller entry point
├── mathcore.spec              # PyInstaller spec
├── build.bat                  # one-shot build pipeline
├── launch_dev.bat             # dev launcher using the venv
├── requirements.txt
└── README.md / README.txt
```

---

## Privacy & data flow

- The app listens **only on `127.0.0.1`**. Nothing is ever bound to a
  public interface; firewall prompts can be safely declined without
  breaking anything.
- The API key is stored in `data\userdata.db` encrypted with AES-GCM,
  using a key derived from `hostname + username` via PBKDF2-SHA256
  (200,000 iterations). Moving the file to a different machine
  invalidates the stored key — by design.
- The only network calls the app makes are HTTPS requests to the
  AI provider you configured.
- Schema migrations are forward-only and tracked in a
  `schema_migrations` table, so an updated build can read DBs from
  older versions without losing rows.

---

## Tech stack

| Layer | Stack |
|---|---|
| Language | Python 3.11 / 3.14, JavaScript (ES2020+) |
| Backend | FastAPI 0.115+, uvicorn, aiosqlite, httpx, pydantic 2 |
| Frontend | React 18, Vite 5, react-router 6, react-markdown, remark-math, rehype-katex, KaTeX |
| Crypto | `cryptography` (AES-GCM, PBKDF2-SHA256) |
| Packaging | PyInstaller 6 |
| Storage | SQLite (rollback-journal mode, `busy_timeout=5000`) |

---

## License

This project is provided as-is. Pick whatever license suits you and
add it as `LICENSE` if you intend to distribute.
