from functools import lru_cache

from app.config import get_settings
from app.core.campaign_registry import CampaignRegistry
from app.core.result_loader import ResultLoader
from app.workers.job_store import JobStore


@lru_cache
def get_campaign_registry() -> CampaignRegistry:
    return CampaignRegistry(get_settings())


@lru_cache
def get_result_loader() -> ResultLoader:
    return ResultLoader(get_settings(), get_campaign_registry())


@lru_cache
def get_job_store() -> JobStore:
    return JobStore(get_settings())
