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
        │   ├── Nav.jsx                  # Bottom tab bar
        │   ├── StarRating.jsx           # 1–5 star widget, half-star click/render support
        │   ├── Badge.jsx                # Coloured pill chip
        │   ├── ReviewGate.jsx           # Non-dismissible pending-review modal
        │   ├── PhotoUploader.jsx        # Shared upload button+input (RecipeDetail + CookingMode)
        │   └── ActiveSessionBanner.jsx  # Ambient "X is cooking — nog Y min" banner, polls /sessions/active
        └── pages/
            ├── Home.jsx         # Dashboard: recent + top-rated
            ├── RecipeList.jsx   # Filterable recipe list (vegetarian/baking/difficulty chips)
            ├── RecipeDetail.jsx # Recipe view, cook sessions, edit/delete own ratings+photos
            ├── RecipeForm.jsx   # Create / edit recipe + URL import
            ├── CookingMode.jsx  # Guided step-by-step cooking flow (wake lock, timers, finish+photo)
            ├── Planner.jsx      # Weekly planner, side dishes, past-day handling, grocery list modal
            └── Settings.jsx     # Identity picker + app version + update check
```

Backend tests live in `backend/tests/` (pytest, `pytest.ini`, `requirements-dev.txt`); frontend tests sit next to the code they cover (`*.test.js` / `*.test.jsx`). See **Testing** below.

---

## Data model

```
recipes          — id, name, description, cook_time, difficulty, cuisine_type,
                   is_vegetarian, is_vegan, is_side_dish, is_baking, created_at
ingredients      — id, recipe_id, name, amount, unit, sort_order
steps            — id, recipe_id, sort_order, description
cook_sessions    — id, recipe_id, cooked_at, notes, cooked_by (michael|rachel, nullable),
                   cooking_mode (bool), current_step, step_started_at, timer_seconds,
                   timer_started_at, finished_at (nullable — NULL = still cooking)
photos           — id, cook_session_id, file_path, uploaded_at, uploaded_by (michael|rachel, nullable)
ratings          — id, cook_session_id, user (michael|rachel), stars (1–5, 0.5 steps), rated_at
                   UNIQUE(cook_session_id, user)
meal_plan        — id, week_start, day (mon–sun), recipe_id, locked
                   UNIQUE(week_start, day)
meal_plan_sides  — id, week_start, day (mon–sun), recipe_id
                   UNIQUE(week_start, day, recipe_id) — multiple side dishes per day
```

Note: `ratings.stars` is still declared `INTEGER` in SQLite but stores half-star values fine —
SQLite's column-affinity conversion only coerces a REAL to INTEGER when it's lossless, so `3.5`
is stored untouched and the existing `CHECK(stars BETWEEN 1 AND 5)` already accepts it. No
migration was needed; validation (must be a multiple of 0.5) happens in `RatingIn` instead.

---

## API endpoints

| Method | Path                          | Description                        |
|--------|-------------------------------|------------------------------------|
| GET    | /recipes/                     | List recipes (filterable: vegetarian, vegan, difficulty, cuisine, side_dish, baking) |
| POST   | /recipes/                     | Create recipe                      |
| GET    | /recipes/{id}                 | Get recipe with ingredients+steps  |
| PUT    | /recipes/{id}                 | Update recipe                      |
| DELETE | /recipes/{id}                 | Delete recipe                      |
| GET    | /sessions/recipe/{id}         | Sessions for a recipe              |
| POST   | /sessions/                    | Start a cook session (`cooked_by`, `cooking_mode`) |
| GET    | /sessions/active              | Currently in-progress cooking-mode session (or `null`), with computed remaining time |
| GET    | /sessions/{id}                | Get a single session                |
| POST   | /sessions/{id}/step           | Advance cooking mode to a step index |
| POST   | /sessions/{id}/timer          | Start a timer for the current step |
| DELETE | /sessions/{id}/timer          | Cancel the active timer            |
| POST   | /sessions/{id}/finish         | Mark cooking mode finished (unblocks the review gate) |
| POST   | /sessions/{id}/rate           | Rate a session                     |
| DELETE | /sessions/{id}/rate/{user}    | Remove a user's rating for a session |
| GET    | /sessions/pending/{user}      | Sessions `user` still owes a review for |
| POST   | /sessions/{id}/photo          | Upload photo for a session (`uploaded_by` required) |
| DELETE | /sessions/{id}/photo/{photo_id} | Delete a photo (row + file)      |
| GET    | /plan/{week_start}            | Get week plan (ISO date Monday), each day includes `sides` |
| POST   | /plan/suggest/{week_start}    | Generate suggestions (excludes side/baking recipes) |
| PUT    | /plan/{week_start}/{day}      | Set a day's main recipe (400 if it's a side/baking recipe) |
| DELETE | /plan/{week_start}/{day}      | Clear a day (also clears its side dishes) |
| POST   | /plan/{week_start}/{day}/sides | Attach a side dish to a day       |
| DELETE | /plan/{week_start}/{day}/sides/{recipe_id} | Remove a side dish from a day |
| POST   | /plan/grocery                 | Aggregate grocery list for week (mains + sides, excludes past days) |
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
Covers recipe/session/planner CRUD, the pending-review gate queue logic (including the cooking-mode vs legacy-session distinction), meal-plan scoring/cooldown/grocery aggregation, side-dish/baking category rules, cooking-mode step/timer/finish/active-session endpoints, half-star rating validation, review/photo edit-delete, mocked AI-import error paths (no real network/Anthropic calls), and a direct regression test for the `check_same_thread` fix. 67 tests as of the cooking-mode branch merge.

**Frontend** — Vitest + Testing Library:
```bash
cd frontend
npm test
```
Covers `ReviewGate`'s modal/queue behavior, the `api.js`/`user.js` helpers, half-star `StarRating` click/render behavior, `PhotoUploader`, `ActiveSessionBanner` polling, `CookingMode`'s step navigation/timer/wake-lock, `RecipeDetail`'s rating/photo edit-delete affordances, `RecipeList`'s baking filter, and `Planner`'s past-day dimming, side-dish flow, and share-button feedback. 55 tests as of the cooking-mode branch merge. Pinned to `vitest@^2.1.9` + `jsdom@^25` — `vitest@4`'s bundled `vite@8`/rolldown dependency failed to install (native binding + Node-version mismatch) on this project's Windows dev machine; re-evaluate before upgrading, especially on the Pi's ARM64 Linux.

---

## Key design decisions

- **Two fixed users**: Michael and Rachel. Identity stored in `localStorage` per device. Either person can rate on behalf of the other from their own device.
- **Cook sessions**: Every time a recipe is cooked creates a new session, tagged with `cooked_by` (who marked it). Ratings and photos attach to sessions, not recipes. Aggregate rating (`avg_rating`) is computed across all sessions.
- **Review gate**: on app load, `<ReviewGate>` (frontend/src/components/ReviewGate.jsx) checks `GET /sessions/pending/{me}` — finished sessions `me` hasn't rated yet. If any exist, a non-dismissible full-screen modal blocks all interaction (no skip/close) and queues through them one at a time (oldest first); the app becomes usable again once the queue is empty. Historically this only ever prompted the *other* person (not whoever cooked it); see the **Cooking mode** bullet below for how that changed for sessions started via the new guided flow.
- **SQLite connections**: `get_db()` uses `check_same_thread=False` — required because FastAPI runs sync dependencies/endpoints via anyio's threadpool, which does not guarantee the same worker thread across those calls. Without it, requests intermittently (~50% of the time) raised `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`, which surfaced in the UI as recipe pages randomly showing "Niet gevonden." Keep this flag if the connection-per-request pattern in `database.py` ever changes.
- **Meal planner scoring**: base score = avg stars (default 3.0 for unrated), +0.5 bonus for never-rated dishes, −1.5 soft cooldown for dishes cooked within the last 14 days.
- **AI import**: fetches raw HTML (truncated to 40k chars), sends to Haiku with a strict JSON schema prompt. User reviews extracted fields before saving.
- **Grocery list**: aggregated by recipe (mains + side dishes) from the current week's meal plan, excluding past days; shareable via Web Share API with clipboard fallback. The share button used to fail silently (no feedback on success, and an unhandled rejection if the user cancelled the native share sheet) — it now shows an inline "Gedeeld" / "Gekopieerd naar klembord" / "Delen mislukt" banner, staying silent only on a user-cancelled (`AbortError`) share.
- **Photo storage**: uploaded to `backend/uploads/`, served as static files at `/uploads/`. Accepted types: jpg, jpeg, png, webp, heic. Deleting a recipe cascades the `photos` DB rows automatically, but the actual files on disk do not delete themselves — `recipes.py`'s `delete_recipe` explicitly removes them from `UPLOAD_DIR` after the DB commit so they don't leak indefinitely.
- **PWA update checks**: the service worker (`frontend/src/sw.js`) does no fetch-interception/precaching (`injectManifest` with empty `globPatterns`) — its only job is to force every open tab to reload once a *new* SW version activates (`skipWaiting` + `clients.claim()` + `clients.navigate()`). Getting the browser to actually notice a new SW is the hard part: the browser's own background check is throttled to roughly once per 24h, which made real deploys lag on phones. `frontend/src/lib/serviceWorker.js` now calls `registration.update()` explicitly on load and whenever the tab returns to the foreground (`visibilitychange`), bypassing that throttle. Settings also exposes a manual "Controleer op updates" button wired to the same `update()` call — register immediately (not deferred to `window.load`), since the button can be tapped before `load` fires on a slow connection, which previously raced `registrationPromise` and always failed.
- **Version indicator**: both the frontend (git short-hash baked in at build time via `vite.config.js`'s `define: { __APP_VERSION__ }`, computed via `git rev-parse --short HEAD`) and the backend (computed once at import time in `main.py`, exposed via `GET /health`'s `version` field) show the running commit on the Settings page — lets you confirm what's actually deployed without SSHing in.
- **Deploy script (`scripts/update.sh`)**: the desktop shortcut launches it via a non-interactive, non-login `bash -c "..."`, which never sources `~/.bashrc` — since node/npm on the Pi are nvm-managed (added to PATH only there), `npm` was invisible in that context even though it resolves fine over SSH (same class of issue previously fixed for the frontend systemd service in commit `e07609a`). `update.sh` now sources `~/.nvm/nvm.sh` explicitly and `die`s with a clear message if `npm` still isn't found, rather than failing silently mid-script under `set -e`. The desktop shortcut's `Exec=` line (generated by `install.sh`) also used to join every step with `;`, so it always printed "Klaar!" (Done) even when `update.sh` aborted early — fixed to use `&&`/`||` so failure is actually visible. Note: `scripts/update.sh` must stay tracked as executable (`100755`) in git, since the desktop shortcut invokes it as a direct path rather than via `bash update.sh` — this repo is edited from a non-Unix dev machine that doesn't preserve the bit by default, so if it's ever un-set, every `git pull` on the Pi will conflict with the locally-required `chmod +x` until re-fixed with `git update-index --chmod=+x`.
- **Cooking mode** (`CookingMode.jsx`, route `/recipes/:id/cook`) fully replaces the old instant "Gekookt!" log — every cook session now goes through a guided flow: `navigator.wakeLock` keeps the screen on (re-requested on `visibilitychange` since the browser auto-releases it when a tab loses visibility), one recipe step per page with Next/Prev, a regex (`/\d+\s*(minuten|minuut|min)/i`) scans each step's text and offers a tappable timer suggestion (countdown driven by `Date.now()` math, not tick-counting, so backgrounding doesn't desync it — ends with a vibration + synthesized Web Audio beep), and a finish screen prompts for a photo before calling `POST /sessions/{id}/finish`.
  - Rating is **deferred** for both users to the existing `ReviewGate`, not shown immediately — `cook_sessions.cooking_mode` (bool) plus `finished_at` (nullable timestamp, the sole in-progress/done indicator) drive this. `pending_reviews` now reads `finished_at IS NOT NULL AND (cooked_by != user OR cooking_mode = 1)`, so the cook sees their own pending review too, but only for sessions started via the new flow — legacy sessions are backfilled `cooking_mode=0` so the migration doesn't retroactively surface old self-review prompts.
  - The other user sees a live ambient banner (`ActiveSessionBanner.jsx`, polls `GET /sessions/active` every ~15s): "Koken van X in uitvoering — nog Y minuten", where Y is computed server-side from `recipe.cook_time / total_steps` per remaining step, using the actual timer's remaining seconds instead of the flat estimate for whichever step has one running. Falls back to step-count-only progress if the recipe has no `cook_time`.
- **Side dishes & baking categories**: `recipes.is_side_dish` / `is_baking` (booleans, same pattern as `is_vegetarian`/`is_vegan`) exclude a recipe from weekly suggestions and from being picked as a day's *main* dish (`PUT /plan/{week_start}/{day}` returns 400 otherwise). Side dishes attach to a day via a separate `meal_plan_sides` table (many per day, unlike the single nullable `recipe_id` on `meal_plan`) through a dedicated picker restricted to `is_side_dish` recipes; baking is browse/filter-only with no day-attachment. The grocery list merges side-dish ingredients into the same flat `by_recipe` dict as mains.
- **Review/photo editing**: ratings and photos can now be edited/deleted, but only from the owning identity's own device — there's no auth layer anywhere in this app, so this is UI-only gating (`RecipeDetail.jsx` checks `r.user === getUser()` / `photo.uploaded_by === getUser()`), same trust model as everything else. `photos.uploaded_by` is nullable since historical photos predate this column and have no known uploader.
- **Past planner days**: `Planner.jsx` dims any day whose calendar date is before today and hides its edit affordances (lock/clear/pick), but keeps the assigned recipe name visible as a read-only record. `POST /plan/grocery` independently excludes past days' ingredients server-side (`planner.py::_today()`, wrapped for test freezing via monkeypatch).

---

## Environment variables

| Variable             | Required | Description                  |
|----------------------|----------|------------------------------|
| `ANTHROPIC_API_KEY`  | Yes      | For URL-based recipe import  |
