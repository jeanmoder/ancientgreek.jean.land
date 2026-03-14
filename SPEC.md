# Ancientgreek Specification (Current Codebase)

Last updated: March 12, 2026

## 1) Product Overview

`ancientgreek.jean.land` is a learning-focused Ancient Greek web app that combines:

- Local-first dictionary lookup (short definitions)
- Live Logeion dictionary expansion on entry open
- Morphological parsing and syntax highlighting
- TEI-based Greek text reading with line-level tooling
- User text workbench (paste your own Greek)
- About page rendered from markdown

This spec reflects the current code in this repository, not earlier design drafts.

## 2) What Is In Scope Right Now

### Frontend tabs

- `Dictionary`
- `Texts`
- `Textbox` (workbench)
- `About`

### Not currently in the shipped UI/API

- No chat tab
- No `/api/chat/*` router

## 3) Tech Stack

### Backend

- Python `>=3.12`
- FastAPI + Uvicorn
- SQLite via `aiosqlite` (cache table)
- HTTP clients: `httpx`
- XML parsing: `lxml`
- Config: `pydantic-settings`
- NLP model runtime: `spacy<3.8` + odyCy model

### Frontend

- React 19 + TypeScript + Vite
- Tailwind CSS 4
- Zustand for app state

### Fonts / typography

- Brill supported as an optional local install
- Gentium Plus / Noto Serif fallback
- Greek display and text/search inputs use the shared Greek serif stack

## 4) Dependency Snapshot

### Python deps (`pyproject.toml`)

- `fastapi`
- `uvicorn[standard]`
- `httpx`
- `pydantic-settings`
- `aiosqlite`
- `python-dotenv`
- `lxml`
- `spacy<3.8`

Dev extras:

- `pytest`, `pytest-asyncio`, `anyio[trio]`, `ruff`

### Frontend deps (`frontend/package.json`)

- Runtime: `react`, `react-dom`, `zustand`, `tailwindcss`, `@tailwindcss/vite`
- Dev: `vite`, `typescript`, `eslint` stack, React type packages

### Locking

- `uv lock` completed successfully in this repo on March 12, 2026.

## 5) Backend Architecture

### App startup (`backend/main.py`)

On startup:

- Initializes SQLite cache table
- Ensures odyCy model is available (`ensure_odycy_model()`)
- Warms local dictionary indexes (`warm_local_dictionary_cache()`)
- Warms text catalog cache (`texts.get_catalog()`)

Routers mounted under `/api`:

- `/dictionary`
- `/texts`

Health endpoint:

- `GET /api/health` -> `{ "status": "ok" }`

### Request guard / security

- CORS allowlist from `ALLOWED_ORIGINS`
- Host header allowlist from `ALLOWED_HOSTS`
- Optional origin/referer enforcement for protected mutating paths
- By default, `/api/dictionary/translate` is protected for POST

## 6) Data Sources

### Dictionaries

Local first:

- `backend/data/lsj-shortdefs.json`
- `backend/data/dictionaries/middle-liddell-short.dat`
- `backend/data/dictionaries/autenrieth-short.dat`

Behavior notes:

- Latin dictionary data is intentionally excluded from active lookup results (`lewis` blocked locally; Latin live dictionaries filtered out)
- Local definitions are short definitions only

Optional long LSJ HTML:

- `backend/data/dictionaries/lsj-full.json`
- If missing, backend can fetch from `LSJ_FULL_S3_URI` (default `s3://ancientgreek/dictionaries/lsj-full.json`)

Live dictionaries:

- Logeion detail endpoint (`anastrophe.uchicago.edu/logeion-api/detail`)
- Used only for full-entry view on dictionary page (`live=true` flow)

### Morphology / syntax / translation

- Morpheus API (`morph.alpheios.net`) for morphology
- Perseus morph page parsing for parse-percent ranking context
- odyCy model via spaCy for syntax roles
- OpenRouter chat completions API for translation (`TRANSLATE_MODEL` default `google/gemini-2.5-flash`)

### Texts

- TEI XML fetched from GitHub raw content using `source_repo/source_branch/github_path` in catalog
- Parsed on the fly from TEI (`lxml`)
- Catalog metadata enriched from TEI title/date + dialect inference heuristics

## 7) Dictionary Behavior (Current UX/Flow)

### Search and entry view

- Dictionary search input accepts Greek, English gloss terms, or transliteration
- `/api/dictionary/full` returns:
  - morphology parses
  - transliteration
  - local definitions
  - paradigms (Wiktionary first, rule-based fallback)
  - citation form

### Local-first + live split

- Initial search stays local-first
- When user opens a word entry (`openEntry`), frontend does:
  1. local `/dictionary/full` (fast + short defs)
  2. live `/dictionary/full?live=true` for Logeion tabs

### Live rendering

- Live results are shown as source tabs (one tab per dictionary)
- All available (non-Latin) Logeion sources are displayed
- Greek HTML is rendered with the shared Greek serif styling (`logeion-entry`)

### Selection popup call policy

- Text selection popups do **not** trigger live Logeion API calls
- Selection uses local endpoints only:
  - single-word: `/dictionary/full`
  - multi-word: `/dictionary/parse-text` (+ `/dictionary/translate`)

## 8) Texts Behavior (Current UX/Flow)

### Catalog

- Grouped by author with normalization rules
- Bible-like IDs consolidated under `Bible (Greek)`
- Display title format: English first, Greek in brackets when both exist

### Reader

- Book selector supports:
  - generic labels -> numeric style
  - non-generic labels -> label text
  - repeated labels disambiguated (`Episode 1`, `Episode 2`, ...)
  - hides selector when only `Full Text`
- Line counts shown in selector and near passage header
- Pagination: 50 lines/page
- Line-level syntax toggle (`Σ`), with color legend in sidebar
- Side sentence panel (desktop) with:
  - parsing view
  - translation view
- Popup/panel sizing clamps to viewport and enables scrolling

### Heuristic in-text headers

- Very short all-caps-ish lines are rendered in faint header style (frontend heuristic)

## 9) Workbench (Textbox)

- User can paste/provide arbitrary Ancient Greek text
- Paste filtering keeps Ancient Greek relevant characters
- Supports syntax parse toggle for whole text
- Supports the same highlight-popup workflows as other Greek text areas

## 10) About Page

- `frontend/public/about.md` is fetched at runtime and rendered in-app
- Lightweight custom markdown parser supports headers, paragraphs, lists, links, images
- URLs are rendered in highlight red style
- Relative image links resolve via app base URL

## 11) API Surface (Current)

### Dictionary

- `GET /api/dictionary/parse`
- `GET /api/dictionary/lookup`
- `GET /api/dictionary/full`
- `POST /api/dictionary/parse-text`
- `POST /api/dictionary/translate`

### Texts

- `GET /api/texts/catalog`
- `GET /api/texts/books/{text_id}`
- `GET /api/texts/read/{text_id}`
- `POST /api/texts/syntax`

### Health

- `GET /api/health`

## 12) Caching

SQLite `cache` table is used for:

- morphology results
- full dictionary lookups
- parse-text results
- syntax results
- translation results
- text passages
- live Logeion payloads

No chat history table is currently retained (legacy chat table is dropped at init).

## 13) Deployment Notes

Primary documented target: AWS Lightsail + Nginx reverse proxy.

- Frontend served as static build
- Backend runs as systemd service on `127.0.0.1:8000`
- `/api/*` proxied through Nginx
- Translate endpoint has tighter rate limiting/origin checks
- LSJ full file can be synced from S3 during install/redeploy

See:

- `DEPLOY_LIGHTSAIL.md`
- `scripts/lightsail/install.sh`
- `scripts/lightsail/redeploy.sh`
- `scripts/lightsail/reload.sh`

Smart reload workflow for post-push updates on Lightsail:

- `sudo bash scripts/lightsail/reload.sh` (`auto`) detects changed files and runs the lightest valid deploy step.
- `public` mode syncs `frontend/public` only (best for `about.md`, demo images, and other static public assets).
- `frontend` mode rebuilds frontend and syncs static output.
- `backend` mode reinstalls backend package and restarts the backend service.
- `full` mode performs both backend and frontend steps.
- Both `reload.sh` and `redeploy.sh` resync nginx `X-Internal-Api-Key` from `/etc/ancientgreek/ancientgreek.env` before reloading services.

Update run order for the next release:

1. Push your commit to GitHub.
2. SSH into Lightsail and enter app dir: `cd /opt/ancientgreek/app`.
3. Run `sudo bash scripts/lightsail/reload.sh` (recommended default).
4. If you rotated `INTERNAL_API_KEY` in `/etc/ancientgreek/ancientgreek.env`, run `sudo bash scripts/lightsail/reload.sh backend` (or `full`) so backend process and nginx header stay in sync.
5. Verify: `curl -sS https://ancientgreek.jean.land/api/health` and `sudo journalctl -u ancientgreek -n 100 --no-pager`.

## 14) Local Development

```bash
# backend
uv run uvicorn backend.main:app --reload --port 8000

# frontend
cd frontend
npm install
npm run dev

# tests
cd ..
uv run pytest tests/ -v
```

## 15) Test Coverage Snapshot

Current backend tests present:

- `tests/backend/test_dictionary.py`
- `tests/backend/test_texts.py`

No current chat test suite in this repo state.
