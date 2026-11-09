import csv
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.campaign_registry import CampaignRegistry
from app.core.history_management import delete_experiment, delete_local_run
from app.main import app
from app.workers.gpu_scheduler import GPUScheduler
from app.workers.job_store import JobStore


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_run_table(path: Path, run_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["run_id", "pose_id"])
        writer.writeheader()
        for index, run_id in enumerate(run_ids):
            writer.writerow({"run_id": run_id, "pose_id": f"pose_{index}"})


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    workbench = tmp_path / "workbench"
    return Settings(
        repo_root=tmp_path,
        existing_campaign_root=tmp_path / "readonly",
        workbench_output_root=workbench,
        web_cache_root=workbench / "web_cache",
    )


def test_delete_local_run_updates_indexes_and_derivatives(settings: Settings) -> None:
    campaign = settings.workbench_output_root / "campaigns" / "job_test"
    run_ids = ["WEB_job_test", "WEB_job_test_001"]
    for name in ("runs_index.csv", "POSE_METRICS.csv"):
        write_run_table(campaign / "reports" / name, run_ids)
    for run_id in run_ids:
        (campaign / "runs" / run_id).mkdir(parents=True)
    write_json(campaign / "campaign_manifest.json", {"run_ids": run_ids})
    write_json(campaign / "pose_manifest.json", {"poses": [{"run_id": item} for item in run_ids]})
    write_json(settings.workbench_output_root / "jobs" / "job_test" / "status.json", {"status": "complete"})
    (settings.web_cache_root / run_ids[0]).mkdir(parents=True)
    bundle = settings.workbench_output_root / "result_bundles" / f"{run_ids[0]}_analysis_bundle.zip"
    bundle.parent.mkdir(parents=True)
    bundle.touch()
    export = settings.workbench_output_root / "path_exports" / "export_1"
    write_json(export / "manifest.json", {"run_id": run_ids[0]})

    result = delete_local_run(settings, run_ids[0])

    assert result["campaign_deleted"] is False
    assert not (campaign / "runs" / run_ids[0]).exists()
    assert (campaign / "runs" / run_ids[1]).exists()
    assert not (settings.web_cache_root / run_ids[0]).exists()
    assert not bundle.exists()
    assert not export.exists()
    with (campaign / "reports" / "runs_index.csv").open(encoding="utf-8") as f:
        assert [row["run_id"] for row in csv.DictReader(f)] == [run_ids[1]]
    assert json.loads((campaign / "campaign_manifest.json").read_text())["run_ids"] == [run_ids[1]]

    result = delete_local_run(settings, run_ids[1])
    assert result["campaign_deleted"] is True
    assert not campaign.exists()
    assert not (settings.workbench_output_root / "jobs" / "job_test").exists()


def test_active_history_cannot_be_deleted(settings: Settings) -> None:
    experiment_id = "exp_active"
    experiment = settings.workbench_output_root / "experiments" / experiment_id
    write_json(experiment / "experiment_manifest.json", {"experiment_id": experiment_id})
    job = settings.workbench_output_root / "jobs" / "job_active"
    write_json(job / "job.json", {"source_experiment_id": experiment_id})
    write_json(job / "status.json", {"job_id": "job_active", "status": "running"})

    with pytest.raises(RuntimeError, match="正在被任务"):
        delete_experiment(settings, experiment_id)
    assert experiment.exists()

    write_json(job / "status.json", {"job_id": "job_active", "status": "complete"})
    result = delete_experiment(settings, experiment_id)
    assert result["deleted_id"] == experiment_id
    assert not experiment.exists()


def test_readonly_result_delete_is_forbidden() -> None:
    client = TestClient(app)
    response = client.delete("/api/results/MM_C002full_Pp0_p0_BposY_S501_N500k")
    assert response.status_code == 403
    assert "只读基准" in response.json()["detail"]


def test_completed_tasks_are_published_incrementally(settings: Settings) -> None:
    store = JobStore(settings)
    scheduler = GPUScheduler(settings, store)
    request = {
        "scene_id": "scene.xml",
        "mode": "campaign",
        "radar": {"center_m": [0, 0, 1], "look_at_m": [1, 0, 1]},
        "poses": [
            {"center_m": [0, 0, 1], "look_at_m": [1, 0, 1]},
            {"center_m": [0, 1, 1], "look_at_m": [1, 1, 1]},
        ],
    }
    first = {"result": {"run_id": "run_0", "task_index": 0}, "row": {"run_id": "run_0"}}
    second = {"result": {"run_id": "run_1", "task_index": 1}, "row": {"run_id": "run_1"}}

    scheduler._write_partial_artifacts("job_batch", request, [first])
    index = settings.workbench_output_root / "campaigns" / "job_batch" / "reports" / "runs_index.csv"
    with index.open(encoding="utf-8") as f:
        assert [row["run_id"] for row in csv.DictReader(f)] == ["run_0"]

    scheduler._write_partial_artifacts("job_batch", request, [second, first])
    with index.open(encoding="utf-8") as f:
        assert [row["run_id"] for row in csv.DictReader(f)] == ["run_0", "run_1"]


def test_failed_task_artifacts_are_removed(settings: Settings) -> None:
    store = JobStore(settings)
    scheduler = GPUScheduler(settings, store)
    campaign = settings.workbench_output_root / "campaigns" / "job_failed"
    run_id = "WEB_job_failed"
    (campaign / "runs" / run_id).mkdir(parents=True)
    (settings.web_cache_root / run_id).mkdir(parents=True)

    scheduler._cleanup_failed_artifacts("job_failed", {run_id}, remove_campaign=True)

    assert not campaign.exists()
    assert not (settings.web_cache_root / run_id).exists()


def test_scheduler_crash_marks_job_failed_and_cleans_partial_run(settings: Settings, monkeypatch) -> None:
    store = JobStore(settings)
    scheduler = GPUScheduler(settings, store)
    request = {"radar": {"center_m": [0, 0, 1], "look_at_m": [1, 0, 1]}}
    store.create("job_crash", request, [0])
    task = scheduler.expand_tasks(request, [0])[0]
    partial_run = settings.workbench_output_root / "campaigns" / "job_crash" / "runs" / "WEB_job_crash"
    partial_run.mkdir(parents=True)

    def crash(*_args, **_kwargs) -> None:
        raise RuntimeError("scheduler crashed")

    monkeypatch.setattr(scheduler, "_run_background", crash)
    scheduler._run_background_guarded("job_crash", request, [task])

    status = store.load_status("job_crash")
    assert status["status"] == "failed"
    assert status["progress"]["failed_tasks"] == 1
    assert "scheduler crashed" in status["error"]
    assert not partial_run.exists()


def test_registry_ignores_incomplete_and_corrupt_campaigns(settings: Settings) -> None:
    complete = settings.workbench_output_root / "campaigns" / "job_complete"
    incomplete = settings.workbench_output_root / "campaigns" / "job_incomplete"
    corrupt = settings.workbench_output_root / "campaigns" / "job_corrupt"
    write_run_table(complete / "reports" / "runs_index.csv", ["run_complete"])
    write_run_table(incomplete / "reports" / "runs_index.csv", ["run_incomplete"])
    corrupt_table = corrupt / "reports" / "runs_index.csv"
    corrupt_table.parent.mkdir(parents=True)
    corrupt_table.write_bytes(b"\xff\xfe\x00invalid")
    complete_run = complete / "runs" / "run_complete"
    for name in CampaignRegistry.REQUIRED_RUN_FILES:
        path = complete_run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (incomplete / "runs" / "run_incomplete").mkdir(parents=True)

    registry = CampaignRegistry(settings)
    campaigns = registry.list_campaigns()

    assert next(item for item in campaigns if item.campaign_id == "workbench_local").run_count == 1
    assert "run_complete" in registry.build_run_index()
    assert "run_incomplete" not in registry.build_run_index()
    assert all(item.campaign_id not in {"job_incomplete", "job_corrupt"} for item in campaigns)


def test_job_status_json_is_written_atomically(settings: Settings) -> None:
    store = JobStore(settings)
    store.create("job_atomic", {"scene_id": "test"}, [0])
    store.update_status("job_atomic", status="running")

    assert store.load_status("job_atomic")["status"] == "running"
    assert not list(store.job_paths("job_atomic").root.glob("*.tmp"))
    assert not list(store.job_paths("job_atomic").root.glob(".*.tmp"))
