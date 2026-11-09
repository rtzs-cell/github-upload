from app.config import get_settings
import json

from app.core.campaign_registry import Campaign, CampaignRegistry
from app.core.result_loader import ResultLoader


def test_list_campaigns_contains_c002() -> None:
    registry = CampaignRegistry(get_settings())
    campaigns = registry.list_campaigns()
    assert campaigns[0].campaign_id == "c002_full_existing"
    assert campaigns[0].run_count == 30
    assert campaigns[0].readonly is True
    assert campaigns[1].campaign_id == "workbench_local"


def test_local_results_aggregate_excludes_verification_campaigns() -> None:
    registry = CampaignRegistry(get_settings())
    runs = registry.load_runs("workbench_local")
    assert runs
    assert all(run.campaign_id and not run.campaign_id.startswith("tiny_") for run in runs)


def test_list_c002_runs_count_30() -> None:
    registry = CampaignRegistry(get_settings())
    runs = registry.load_runs("c002_full_existing")
    assert len(runs) == 30
    assert runs[0].run_id
    assert runs[0].valid_path_count > 0


def test_load_metadata_does_not_require_cir() -> None:
    settings = get_settings()
    registry = CampaignRegistry(settings)
    loader = ResultLoader(settings, registry)
    response = loader.load_metadata_response("MM_C002full_Pp0_p0_BposY_S501_N500k")
    assert response["run_id"] == "MM_C002full_Pp0_p0_BposY_S501_N500k"
    assert response["available_artifacts"]["cir"] is False
    assert response["metadata"]["run_id"] == "MM_C002full_Pp0_p0_BposY_S501_N500k"


def test_run_summary_reads_persistent_display_name(tmp_path) -> None:
    settings = get_settings()
    registry = CampaignRegistry(settings)
    original = registry.load_runs("c002_full_existing")[0]
    campaign_root = tmp_path / "campaign"
    run_dir = campaign_root / "runs" / original.run_id
    run_dir.mkdir(parents=True)
    (run_dir / "display_name.json").write_text(
        json.dumps({"display_name": "主路口夜间测量"}, ensure_ascii=False),
        encoding="utf-8",
    )
    row = original.model_dump()
    summary = registry._row_to_run_summary(
        row,
        Campaign(campaign_id="local", display_name="local", root=campaign_root, readonly=False),
    )
    assert summary.display_name == "主路口夜间测量"
