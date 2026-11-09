from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.deps import get_job_store
from app.schemas import JobStatusResponse, RadarSimulationRequest, SimulationJobResponse
from app.workers.gpu_scheduler import GPUScheduler

router = APIRouter(prefix="/api/simulations", tags=["simulations"])


def make_job_id(payload: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    digest = sha1(repr(sorted(payload.items())).encode("utf-8")).hexdigest()[:8]
    # A failed retry can happen within the same second with the same payload.
    # Keep the digest for diagnostics, but never reuse its output directory.
    return f"job_{now}_{digest}_{uuid4().hex[:8]}"


@router.post("", response_model=SimulationJobResponse)
def submit_simulation(request: RadarSimulationRequest) -> SimulationJobResponse:
    settings = get_settings()
    job_store = get_job_store()
    scheduler = GPUScheduler(settings, job_store)
    payload = request.model_dump()
    job_id = make_job_id(payload)
    try:
        scheduler.submit_single(job_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return SimulationJobResponse(job_id=job_id, status="queued", status_url=f"/api/simulations/{job_id}")


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job_store = get_job_store()
    try:
        return JobStatusResponse(**job_store.load_status(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
