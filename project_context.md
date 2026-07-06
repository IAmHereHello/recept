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
    ├── index.html
    └── src/
        ├── App.jsx              # Router setup
        ├── main.jsx
        ├── lib/
        │   ├── api.js           # All fetch calls (BASE = '/api')
        │   └── user.js          # localStorage identity (michael | rachel)
        ├── components/
        │   ├── Nav.jsx          # Bottom tab bar
        │   ├── StarRating.jsx   # 1–5 star widget
        │   └── Badge.jsx        # Coloured pill chip
        └── pages/
            ├── Home.jsx         # Dashboard: recent + top-rated
            ├── RecipeList.jsx   # Filterable recipe list
            ├── RecipeDetail.jsx # Recipe view, cook sessions, ratings
            ├── RecipeForm.jsx   # Create / edit recipe + URL import
            ├── Planner.jsx      # Weekly planner + grocery list modal
            └── Settings.jsx     # Identity picker (Michael / Rachel)
```

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
| GET    | /health                       | Health check                       |

---

## Key design decisions

- **Two fixed users**: Michael and Rachel. Identity stored in `localStorage` per device. Either person can rate on behalf of the other from their own device.
- **Cook sessions**: Every time a recipe is cooked creates a new session, tagged with `cooked_by` (who marked it). Ratings and photos attach to sessions, not recipes. Aggregate rating (`avg_rating`) is computed across all sessions.
- **Review gate**: on app load, `<ReviewGate>` (frontend/src/components/ReviewGate.jsx) checks `GET /sessions/pending/{me}` — sessions someone *else* cooked that `me` hasn't rated yet. If any exist, a non-dismissible full-screen modal blocks all interaction (no skip/close) and queues through them one at a time (oldest first); the app becomes usable again once the queue is empty. A session only counts as "pending" for the other person if `cooked_by` is set and no rating row exists yet for them — so if the cook already rated on the other's behalf via the existing "rate for other" checkbox, the gate won't re-prompt.
- **SQLite connections**: `get_db()` uses `check_same_thread=False` — required because FastAPI runs sync dependencies/endpoints via anyio's threadpool, which does not guarantee the same worker thread across those calls. Without it, requests intermittently (~50% of the time) raised `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`, which surfaced in the UI as recipe pages randomly showing "Niet gevonden." Keep this flag if the connection-per-request pattern in `database.py` ever changes.
- **Meal planner scoring**: base score = avg stars (default 3.0 for unrated), +0.5 bonus for never-rated dishes, −1.5 soft cooldown for dishes cooked within the last 14 days.
- **AI import**: fetches raw HTML (truncated to 40k chars), sends to Haiku with a strict JSON schema prompt. User reviews extracted fields before saving.
- **Grocery list**: aggregated by recipe from the current week's meal plan; shareable via Web Share API with clipboard fallback.
- **Photo storage**: uploaded to `backend/uploads/`, served as static files at `/uploads/`. Accepted types: jpg, jpeg, png, webp, heic.

---

## Environment variables

| Variable             | Required | Description                  |
|----------------------|----------|------------------------------|
| `ANTHROPIC_API_KEY`  | Yes      | For URL-based recipe import  |
