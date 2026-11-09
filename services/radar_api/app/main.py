from app.bootstrap import ensure_repo_imports

ensure_repo_imports()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api import campaigns, experiments, health, results, simulations


app = FastAPI(
    title="Radar Sensing Workbench API",
    version="0.3.0",
    description="Radar-only Sionna RT sensing workbench backend.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(experiments.router)
app.include_router(campaigns.router)
app.include_router(results.router)
app.include_router(simulations.router)

frontend_dist = Path(__file__).resolve().parents[3] / "apps" / "radar-workbench" / "dist"
if (frontend_dist / "index.html").exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="radar-workbench")
