from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import Settings


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class JobPaths:
    root: Path
    job_json: Path
    status_json: Path
    task_manifest_json: Path
    events_jsonl: Path
    logs_txt: Path


class JobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs_root = settings.workbench_output_root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)

    def job_paths(self, job_id: str) -> JobPaths:
        root = self.jobs_root / job_id
        return JobPaths(
            root=root,
            job_json=root / "job.json",
            status_json=root / "status.json",
            task_manifest_json=root / "task_manifest.json",
            events_jsonl=root / "worker_events.jsonl",
            logs_txt=root / "logs.txt",
        )

    def create(self, job_id: str, payload: dict[str, Any], gpu_ids: list[int]) -> JobPaths:
        paths = self.job_paths(job_id)
        paths.root.mkdir(parents=True, exist_ok=True)
        status = {
            "job_id": job_id,
            "status": "queued",
            "created_at_utc": utc_now(),
            "started_at_utc": None,
            "completed_at_utc": None,
            "progress": {"total_tasks": 1, "completed_tasks": 0, "failed_tasks": 0},
            "gpu_ids": gpu_ids,
            "current_tasks": [],
            "available_run_ids": [],
            "result": None,
            "error": None,
        }
        self.write_json(paths.job_json, payload)
        self.write_json(paths.status_json, status)
        self.write_json(paths.task_manifest_json, {"job_id": job_id, "tasks": [payload]})
        paths.logs_txt.touch(exist_ok=True)
        return paths

    def read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        temp_path.replace(path)

    def append_event(self, job_id: str, event: dict[str, Any]) -> None:
        paths = self.job_paths(job_id)
        paths.root.mkdir(parents=True, exist_ok=True)
        payload = {"time_utc": utc_now(), **event}
        with paths.events_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True))
            f.write("\n")

    def load_status(self, job_id: str) -> dict[str, Any]:
        return self.read_json(self.job_paths(job_id).status_json)

    def update_status(self, job_id: str, **updates: Any) -> dict[str, Any]:
        paths = self.job_paths(job_id)
        status = self.read_json(paths.status_json)
        status.update(updates)
        self.write_json(paths.status_json, status)
        return status
