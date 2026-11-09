from fastapi import APIRouter

from app.config import get_settings
from app.core.sionna_runtime import probe_sionna_runtime, runtime_summary
from app.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        allowed_gpu_ids=list(settings.allowed_gpu_ids),
        existing_campaign_available=settings.existing_campaign_root.exists(),
        web_cache_root=str(settings.web_cache_root),
        sionna_runtime=runtime_summary(settings),
    )


@router.get("/health/sionna_runtime")
def sionna_runtime_probe() -> dict:
    return probe_sionna_runtime(get_settings())
