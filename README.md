# MedBox

An AI-powered, voice-assisted medicine management app for blind and visually
impaired users — a FastAPI backend (auth, scheduling, OCR-based medicine
recognition) paired with a React + Vite frontend (voice-first UI, dose
tracking, caregiver dashboard).

```
medbox-dev/
├── backend/     FastAPI app — auth, medicines, reminders, recognition, vitals, caregiver, AI agent
├── frontend/    React + Vite app — voice UI, schedule, library, caregiver dashboard
├── run_backend.py / run_backend.sh   Launchers (see "Run it" below)
└── .gitignore
```

## Prerequisites

- Python 3.12
- Node.js 20+ and npm
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed and on
  your `PATH` (optional — the real medicine-scan OCR path needs it; without
  it the backend falls back to a labelled simulated read, so the app still
  runs)

## Setup

```bash
# from the project root (the parent of backend/ and frontend/)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt

cd frontend
npm install
cd ..
```

## Run it

Both servers need to be running at the same time — sign-in and all data
goes through the real backend.

```bash
# Terminal 1 — backend (run from the project root)
python run_backend.py --reload
# or: ./run_backend.sh

# Terminal 2 — frontend
cd frontend
npm run dev
```

Then open the URL Vite prints (typically `http://localhost:5173`). The dev
server proxies `/api/*` to `http://localhost:8000`, so no extra config is
needed for email/password sign-in.

The backend seeds two accounts on first run (`backend/seed.py`):

| Role       | Email                         | Password           |
|------------|--------------------------------|---------------------|
| Primary user | `maya.lin@medbox.health`     | `securePass123`     |
| Caregiver    | `dr.jenkins@medbox.health`   | `caregiverPass123`  |

Interactive API docs are served at `http://localhost:8000/docs`.

### Environment variables

| Variable | Where | Required? | Purpose |
|---|---|---|---|
| `GROQ_API_KEY` | backend | optional | Powers the AI voice assistant (`/api/agent/chat`). Without it, the endpoint replies with a "not configured yet" message instead of erroring. Free key: https://console.groq.com |
| `VITE_FIREBASE_*` (6 vars) | `frontend/.env` | optional | Enables the "Continue with Google" button. Copy `frontend/.env.example` → `frontend/.env` and fill in your own Firebase project's values (see comments in that file for the 5-minute setup). Without it, email/password sign-in still works fully. |

`frontend/.env` is git-ignored on purpose — never commit real keys there;
use `.env.example` as the template.

## Running tests

```bash
cd backend
pytest
```

Also included:
- `backend/benchmark.py` / `backend/generate_ground_truth.py` — OCR/date-extraction
  accuracy benchmarking against `backend/datasets/expiry_kaggle/`.

## Docker

Each side has its own `Dockerfile` (`backend/Dockerfile`, `frontend/Dockerfile`)
for running the API and dev server in containers independently; there's no
top-level `docker-compose.yml` yet, so build/run each image separately, e.g.:

```bash
docker build -t medbox-backend ./backend
docker run -p 8000:8000 -e GROQ_API_KEY=... medbox-backend

docker build -t medbox-frontend ./frontend
docker run -p 5173:5173 medbox-frontend
```

## What's inside

**Backend** (`backend/`)
- `main.py` — FastAPI app, CORS, router wiring, startup/shutdown lifecycle
- `routers/` — `auth`, `medicines`, `recognition`, `reminders`, `logs`,
  `caregiver`, `vitals`, `agent` (AI voice assistant)
- `services/` — OCR pipeline, medicine matching, date/expiry extraction,
  text normalization, notifications, drug-interaction checks
- `perception/` — the real image-recognition pipeline (preprocessing, OCR,
  date extraction, medicine matching)
- `scheduler.py` — in-process reminder scheduler (APScheduler; see its
  docstring for the Celery+Redis production path)
- `database.py`, `models.py`, `schemas.py`, `security.py` — SQLAlchemy models,
  Pydantic schemas, JWT auth
- `data/` — bundled medicine reference data used by the matcher at runtime
- `datasets/` — Kaggle expiry-date dataset used only for benchmarking, not
  runtime
- `tests/` — pytest suite (unit + integration)

**Frontend** (`frontend/`) — see `frontend/README.md` for the full feature
breakdown (React Router pages, Zustand store, voice hooks, scan flow,
caregiver charts, accessibility settings, design system).

## Notes on this repo

This repo has been cleaned of everything that's regenerated automatically:
`node_modules/`, `venv/`, `frontend/dist/`, `__pycache__/`, `.pytest_cache/`,
and the local `backend/medbox.db` (recreated on first run). See `.gitignore`
for the full list — none of it needs to be committed or restored manually.
"# medbox_new" 
