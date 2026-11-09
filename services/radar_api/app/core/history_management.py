from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.paths import ensure_within


ACTIVE_JOB_STATUSES = {"queued", "running"}
STALE_JOB_HOURS = 24.0


def job_status_is_active(status: dict[str, Any]) -> bool:
    if status.get("status") not in ACTIVE_JOB_STATUSES:
        return False
    timestamp = status.get("started_at_utc") or status.get("created_at_utc")
    if not timestamp:
        return True
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return True
    return age.total_seconds() <= STALE_JOB_HOURS * 3600.0


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def active_job_for_experiment(settings: Settings, experiment_id: str) -> str | None:
    jobs_root = settings.workbench_output_root / "jobs"
    if not jobs_root.exists():
        return None
    for job_dir in jobs_root.iterdir():
        job_path = job_dir / "job.json"
        status_path = job_dir / "status.json"
        if not job_path.exists() or not status_path.exists():
            continue
        try:
            request = read_json(job_path)
            status = read_json(status_path)
        except (OSError, ValueError):
            continue
        if request.get("source_experiment_id") == experiment_id and job_status_is_active(status):
            return str(status.get("job_id") or job_dir.name)
    return None


def delete_experiment(settings: Settings, experiment_id: str) -> dict[str, Any]:
    experiments_root = settings.workbench_output_root / "experiments"
    experiment_dir = ensure_within(experiments_root / experiment_id, experiments_root)
    if not (experiment_dir / "experiment_manifest.json").exists():
        raise FileNotFoundError(experiment_id)
    active_job = active_job_for_experiment(settings, experiment_id)
    if active_job:
        raise RuntimeError(f"实验方案正在被任务 {active_job} 使用，任务结束后才能删除")
    shutil.rmtree(experiment_dir)
    return {"kind": "experiment", "deleted_id": experiment_id, "deleted_files": True}


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _campaign_containing_run(settings: Settings, run_id: str) -> tuple[Path, list[dict[str, str]]]:
    campaigns_root = settings.workbench_output_root / "campaigns"
    if not campaigns_root.exists():
        raise FileNotFoundError(run_id)
    for campaign_dir in campaigns_root.iterdir():
        if not campaign_dir.is_dir():
            continue
        table_path = campaign_dir / "reports" / "runs_index.csv"
        if not table_path.exists():
            table_path = campaign_dir / "reports" / "POSE_METRICS.csv"
        if not table_path.exists():
            continue
        _, rows = _read_csv(table_path)
        if any(row.get("run_id") == run_id for row in rows):
            return ensure_within(campaign_dir, campaigns_root), rows
    raise FileNotFoundError(run_id)


def _assert_job_inactive(settings: Settings, campaign_id: str) -> None:
    status_path = settings.workbench_output_root / "jobs" / campaign_id / "status.json"
    if not status_path.exists():
        return
    status = read_json(status_path)
    if job_status_is_active(status):
        raise RuntimeError(f"仿真任务仍处于{status.get('status')}状态，结束后才能删除")


def _remove_run_derivatives(settings: Settings, run_id: str) -> None:
    cache_dir = settings.web_cache_root / run_id
    if cache_dir.exists():
        shutil.rmtree(ensure_within(cache_dir, settings.web_cache_root))

    bundles_root = settings.workbench_output_root / "result_bundles"
    if bundles_root.exists():
        for path in bundles_root.glob(f"{run_id}*"):
            if path.is_file():
                ensure_within(path, bundles_root).unlink()

    exports_root = settings.workbench_output_root / "path_exports"
    if exports_root.exists():
        for export_dir in exports_root.iterdir():
            manifest_path = export_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                matches = read_json(manifest_path).get("run_id") == run_id
            except (OSError, ValueError):
                matches = False
            if matches:
                shutil.rmtree(ensure_within(export_dir, exports_root))


def delete_local_run(settings: Settings, run_id: str) -> dict[str, Any]:
    campaign_dir, indexed_rows = _campaign_containing_run(settings, run_id)
    campaign_id = campaign_dir.name
    _assert_job_inactive(settings, campaign_id)
    remaining = [row for row in indexed_rows if row.get("run_id") != run_id]
    run_dir = ensure_within(campaign_dir / "runs" / run_id, campaign_dir)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    _remove_run_derivatives(settings, run_id)

    if not remaining:
        shutil.rmtree(campaign_dir)
        job_dir = settings.workbench_output_root / "jobs" / campaign_id
        if job_dir.exists():
            shutil.rmtree(ensure_within(job_dir, settings.workbench_output_root / "jobs"))
        return {
            "kind": "run",
            "deleted_id": run_id,
            "campaign_id": campaign_id,
            "campaign_deleted": True,
        }

    reports_dir = campaign_dir / "reports"
    for name in ("runs_index.csv", "POSE_METRICS.csv"):
        path = reports_dir / name
        if path.exists():
            fieldnames, rows = _read_csv(path)
            _write_csv(path, fieldnames, [row for row in rows if row.get("run_id") != run_id])

    manifest_path = campaign_dir / "campaign_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        manifest["run_ids"] = [item for item in manifest.get("run_ids", []) if item != run_id]
        write_json(manifest_path, manifest)
    pose_path = campaign_dir / "pose_manifest.json"
    if pose_path.exists():
        pose_manifest = read_json(pose_path)
        pose_manifest["poses"] = [item for item in pose_manifest.get("poses", []) if item.get("run_id") != run_id]
        write_json(pose_path, pose_manifest)
    return {
        "kind": "run",
        "deleted_id": run_id,
        "campaign_id": campaign_id,
        "campaign_deleted": False,
    }
