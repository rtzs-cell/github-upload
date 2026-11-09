from fastapi import APIRouter, HTTPException

from app.deps import get_campaign_registry
from app.schemas import CampaignListResponse, RunsResponse

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("", response_model=CampaignListResponse)
def list_campaigns() -> CampaignListResponse:
    registry = get_campaign_registry()
    return CampaignListResponse(campaigns=registry.list_campaigns())


@router.get("/{campaign_id}/runs", response_model=RunsResponse)
def list_runs(campaign_id: str) -> RunsResponse:
    registry = get_campaign_registry()
    try:
        runs = registry.load_runs(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing campaign file: {exc}") from exc
    return RunsResponse(campaign_id=campaign_id, runs=runs)
