# ReceptApp — Project Context

Personal recipe manager and weekly meal planner for Rachel and Michael, hosted on a Raspberry Pi 5 via Tailscale.

---

## Stack

| Layer      | Technology                              | Port  |
|------------|-----------------------------------------|-------|
| Frontend   | React 19 + Vite + Tailwind v4 + PWA    | 3001  |
| Backend    | FastAPI (Python) + Uvicorn             | 8001  |
| Database   | SQLite (`backend/receptapp.db`)        | —     |
| AI import  | Claude Haiku (`claude-haiku-4-5-20251001`) | —  |

---

## Running locally

```bash
# Backend
cd backend
python -m venv venv && venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8001

# Frontend (new terminal)
cd frontend
npm install
npm run dev        # http://localhost:3001
```

Vite proxies `/api/*` and `/uploads/*` to the backend on port 8001.

---

## Project structure

```
ReceptApp/
├── backend/
│   ├── main.py                  # FastAPI app, lifespan, middleware, mounts
│   ├── requirements.txt
│   ├── receptapp.db             # SQLite database (git-ignored)
│   ├── uploads/                 # Uploaded photos (git-ignored)
│   └── app/
│       ├── config.py            # Shared paths (UPLOAD_DIR)
│       ├── database.py          # SQLite connection, init_db()
│       ├── models.py            # Pydantic schemas
│       └── routers/
│           ├── recipes.py       # CRUD for recipes + ingredients + steps
│           ├── sessions.py      # Cook sessions, ratings, photo uploads
│           ├── planner.py       # Weekly meal plan, suggestions, grocery list
│           └── import_recipe.py # AI-powered URL → recipe import
└── frontend/
    ├── vite.config.js
    ├── vitest.config.js
    ├── vitest.setup.js
    ├── index.html
    └── src/
        ├── App.jsx              # Router setup
        ├── main.jsx
        ├── lib/
        │   ├── api.js           # All fetch calls (BASE = '/api'); /health bypasses it (unprefixed)
        │   ├── user.js          # localStorage identity (michael | rachel)
        │   └── serviceWorker.js # SW registration + proactive update() checks
        ├── components/
        │   ├── Nav.jsx          # Bottom tab bar
        │   ├── StarRating.jsx   # 1–5 star widget
        │   ├── Badge.jsx        # Coloured pill chip
        │   └── ReviewGate.jsx   # Non-dismissible pending-review modal
        └── pages/
            ├── Home.jsx         # Dashboard: recent + top-rated
            ├── RecipeList.jsx   # Filterable recipe list
            ├── RecipeDetail.jsx # Recipe view, cook sessions, ratings
            ├── RecipeForm.jsx   # Create / edit recipe + URL import
            ├── Planner.jsx      # Weekly planner + grocery list modal
            └── Settings.jsx     # Identity picker + app version + update check
```

Backend tests live in `backend/tests/` (pytest, `pytest.ini`, `requirements-dev.txt`); frontend tests sit next to the code they cover (`*.test.js` / `*.test.jsx`). See **Testing** below.

---

## Data model

```
recipes          — id, name, description, cook_time, difficulty, cuisine_type,
                   is_vegetarian, is_vegan, created_at
ingredients      — id, recipe_id, name, amount, unit, sort_order
steps            — id, recipe_id, sort_order, description
cook_sessions    — id, recipe_id, cooked_at, notes, cooked_by (michael|rachel, nullable)
photos           — id, cook_session_id, file_path, uploaded_at
ratings          — id, cook_session_id, user (michael|rachel), stars (1–5), rated_at
                   UNIQUE(cook_session_id, user)
meal_plan        — id, week_start, day (mon–sun), recipe_id, locked
                   UNIQUE(week_start, day)
```

---

## API endpoints

| Method | Path                          | Description                        |
|--------|-------------------------------|------------------------------------|
| GET    | /recipes/                     | List recipes (filterable)          |
| POST   | /recipes/                     | Create recipe                      |
| GET    | /recipes/{id}                 | Get recipe with ingredients+steps  |
| PUT    | /recipes/{id}                 | Update recipe                      |
| DELETE | /recipes/{id}                 | Delete recipe                      |
| GET    | /sessions/recipe/{id}         | Sessions for a recipe              |
| POST   | /sessions/                    | Start a cook session (accepts `cooked_by`) |
| POST   | /sessions/{id}/rate           | Rate a session                     |
| GET    | /sessions/pending/{user}      | Sessions `user` still owes a review for |
| POST   | /sessions/{id}/photo          | Upload photo for a session         |
| GET    | /plan/{week_start}            | Get week plan (ISO date Monday)    |
| POST   | /plan/suggest/{week_start}    | Generate suggestions               |
| PUT    | /plan/{week_start}/{day}      | Set a day's recipe                 |
| DELETE | /plan/{week_start}/{day}      | Clear a day                        |
| POST   | /plan/grocery                 | Aggregate grocery list for week    |
| POST   | /import/                      | Import recipe from URL via AI      |
| GET    | /health                       | Health check + running git short-hash (`version`) |

---

## Testing

**Backend** — pytest + FastAPI `TestClient`, each test gets its own isolated temp SQLite file (no shared state, no need to mock the DB):
```bash
cd backend
venv\Scripts\pytest -q      # Windows
venv/bin/pytest -q          # Linux/Pi
```
Covers recipe/session/planner CRUD, the pending-review gate queue logic, meal-plan scoring/cooldown/grocery aggregation, mocked AI-import error paths (no real network/Anthropic calls), and a direct regression test for the `check_same_thread` fix.

**Frontend** — Vitest + Testing Library:
```bash
cd frontend
npm test
```
Covers `ReviewGate`'s modal/queue behavior and the `api.js`/`user.js` helpers. Pinned to `vitest@^2.1.9` + `jsdom@^25` — `vitest@4`'s bundled `vite@8`/rolldown dependency failed to install (native binding + Node-version mismatch) on this project's Windows dev machine; re-evaluate before upgrading, especially on the Pi's ARM64 Linux.

---

## Key design decisions

- **Two fixed users**: Michael and Rachel. Identity stored in `localStorage` per device. Either person can rate on behalf of the other from their own device.
- **Cook sessions**: Every time a recipe is cooked creates a new session, tagged with `cooked_by` (who marked it). Ratings and photos attach to sessions, not recipes. Aggregate rating (`avg_rating`) is computed across all sessions.
- **Review gate**: on app load, `<ReviewGate>` (frontend/src/components/ReviewGate.jsx) checks `GET /sessions/pending/{me}` — sessions someone *else* cooked that `me` hasn't rated yet. If any exist, a non-dismissible full-screen modal blocks all interaction (no skip/close) and queues through them one at a time (oldest first); the app becomes usable again once the queue is empty. A session only counts as "pending" for the other person if `cooked_by` is set and no rating row exists yet for them — so if the cook already rated on the other's behalf via the existing "rate for other" checkbox, the gate won't re-prompt.
- **SQLite connections**: `get_db()` uses `check_same_thread=False` — required because FastAPI runs sync dependencies/endpoints via anyio's threadpool, which does not guarantee the same worker thread across those calls. Without it, requests intermittently (~50% of the time) raised `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`, which surfaced in the UI as recipe pages randomly showing "Niet gevonden." Keep this flag if the connection-per-request pattern in `database.py` ever changes.
- **Meal planner scoring**: base score = avg stars (default 3.0 for unrated), +0.5 bonus for never-rated dishes, −1.5 soft cooldown for dishes cooked within the last 14 days.
- **AI import**: fetches raw HTML (truncated to 40k chars), sends to Haiku with a strict JSON schema prompt. User reviews extracted fields before saving.
- **Grocery list**: aggregated by recipe from the current week's meal plan; shareable via Web Share API with clipboard fallback.
- **Photo storage**: uploaded to `backend/uploads/`, served as static files at `/uploads/`. Accepted types: jpg, jpeg, png, webp, heic. Deleting a recipe cascades the `photos` DB rows automatically, but the actual files on disk do not delete themselves — `recipes.py`'s `delete_recipe` explicitly removes them from `UPLOAD_DIR` after the DB commit so they don't leak indefinitely.
- **PWA update checks**: the service worker (`frontend/src/sw.js`) does no fetch-interception/precaching (`injectManifest` with empty `globPatterns`) — its only job is to force every open tab to reload once a *new* SW version activates (`skipWaiting` + `clients.claim()` + `clients.navigate()`). Getting the browser to actually notice a new SW is the hard part: the browser's own background check is throttled to roughly once per 24h, which made real deploys lag on phones. `frontend/src/lib/serviceWorker.js` now calls `registration.update()` explicitly on load and whenever the tab returns to the foreground (`visibilitychange`), bypassing that throttle. Settings also exposes a manual "Controleer op updates" button wired to the same `update()` call — register immediately (not deferred to `window.load`), since the button can be tapped before `load` fires on a slow connection, which previously raced `registrationPromise` and always failed.
- **Version indicator**: both the frontend (git short-hash baked in at build time via `vite.config.js`'s `define: { __APP_VERSION__ }`, computed via `git rev-parse --short HEAD`) and the backend (computed once at import time in `main.py`, exposed via `GET /health`'s `version` field) show the running commit on the Settings page — lets you confirm what's actually deployed without SSHing in.
- **Deploy script (`scripts/update.sh`)**: the desktop shortcut launches it via a non-interactive, non-login `bash -c "..."`, which never sources `~/.bashrc` — since node/npm on the Pi are nvm-managed (added to PATH only there), `npm` was invisible in that context even though it resolves fine over SSH (same class of issue previously fixed for the frontend systemd service in commit `e07609a`). `update.sh` now sources `~/.nvm/nvm.sh` explicitly and `die`s with a clear message if `npm` still isn't found, rather than failing silently mid-script under `set -e`. The desktop shortcut's `Exec=` line (generated by `install.sh`) also used to join every step with `;`, so it always printed "Klaar!" (Done) even when `update.sh` aborted early — fixed to use `&&`/`||` so failure is actually visible. Note: `scripts/update.sh` must stay tracked as executable (`100755`) in git, since the desktop shortcut invokes it as a direct path rather than via `bash update.sh` — this repo is edited from a non-Unix dev machine that doesn't preserve the bit by default, so if it's ever un-set, every `git pull` on the Pi will conflict with the locally-required `chmod +x` until re-fixed with `git update-index --chmod=+x`.

---

## Environment variables

| Variable             | Required | Description                  |
|----------------------|----------|------------------------------|
| `ANTHROPIC_API_KEY`  | Yes      | For URL-based recipe import  |
