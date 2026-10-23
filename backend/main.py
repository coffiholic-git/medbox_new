"""
MedBox FastAPI backend — Layer 2 (API Gateway / Backend) from Section 9.

Owns auth, request validation, and routing to the modular routers
described in Section 15's work-division matrix. Long-running
recognition work is delegated to backend/services/ocr_service.py; the
reminder scheduler in backend/scheduler.py runs alongside the API in
the same process for this single-instance demo (see scheduler.py's
docstring for the Celery+Redis production path).
"""
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import agent, auth, caregiver, logs, medicines, recognition, reminders, vitals
from backend.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    print("MedBox backend started. Interactive docs: http://localhost:8000/docs")
    yield
    shutdown_scheduler()


app = FastAPI(
    title="MedBox API",
    description=(
        "Backend for MedBox — an AI-powered, voice-assisted medicine "
        "management system for blind and visually impaired users. "
        "Implements FR1-FR14 from the MedBox product documentation."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Dev-permissive CORS so the Vite dev server (and any origin during the
# demo) can reach the API. Auth is a bearer JWT (not cookies), so
# allow_credentials stays False — that's what makes allow_origins=["*"]
# valid at all; tighten allow_origins to the deployed frontend URL
# before shipping this beyond a demo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(medicines.router)
app.include_router(recognition.router)
app.include_router(reminders.router)
app.include_router(logs.router)
app.include_router(vitals.router)
app.include_router(caregiver.router)
app.include_router(agent.router)


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "MedBox FastAPI Backend",
        "docs": "/docs",
        "timestamp": datetime.now().isoformat(),
    }
