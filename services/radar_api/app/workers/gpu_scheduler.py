from __future__ import annotations

import multiprocessing as mp
import os
from queue import Empty
import shutil
import traceback
from dataclasses import dataclass
from threading import Thread
from typing import Any

from app.config import Settings
from app.workers.job_store import JobStore, utc_now
from app.workers.simulation_worker import SimulationWorker, write_pose_metrics


@dataclass
class ScheduledTask:
    task_index: int
    gpu_id: int
    radar_override: dict[str, Any]


def task_run_id(job_id: str, task_index: int) -> str:
    return f"WEB_{job_id}" if task_index == 0 else f"WEB_{job_id}_{task_index:03d}"


def _worker_entry(
    settings: Settings,
    job_id: str,
    request: dict[str, Any],
    gpu_id: int,
    tasks: list[dict[str, Any]],
    queue: mp.Queue,
) -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    job_store = JobStore(settings)
    worker = SimulationWorker(settings, job_store)
    for task in tasks:
        task_index = int(task["task_index"])
        radar_override = dict(task["radar_override"])
        queue.put(
            {
                "status": "start",
                "gpu_id": gpu_id,
                "task_index": task_index,
                "run_id": task_run_id(job_id, task_index),
            }
        )
        try:
            result = worker.run_task(
                job_id,
                request,
                task_index=task_index,
                radar_override=radar_override,
                gpu_id=gpu_id,
            )
            queue.put({"status": "ok", "gpu_id": gpu_id, "task_index": task_index, "result": result})
        except Exception as exc:
            queue.put(
                {
                    "status": "error",
                    "gpu_id": gpu_id,
                    "task_index": task_index,
                    "run_id": task_run_id(job_id, task_index),
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
            )
            return
    queue.put({"status": "worker_done", "gpu_id": gpu_id})


class GPUScheduler:
    def __init__(self, settings: Settings, job_store: JobStore):
        self.settings = settings
        self.job_store = job_store

    def validate_gpu_ids(self, gpu_ids: list[int]) -> None:
        allowed = set(self.settings.allowed_gpu_ids)
        invalid = [gpu for gpu in gpu_ids if gpu not in allowed]
        if invalid:
            raise ValueError(f"Invalid GPU IDs: {invalid}. Allowed: {sorted(allowed)}")
        if not gpu_ids:
            raise ValueError("At least one GPU ID is required")

    def expand_tasks(self, request: dict[str, Any], gpu_ids: list[int]) -> list[ScheduledTask]:
        raw_poses = request.get("poses") if request.get("mode") == "campaign" else None
        poses = raw_poses or [
            {
                "center_m": request["radar"]["center_m"],
                "look_at_m": request["radar"]["look_at_m"],
            }
        ]
        tasks: list[ScheduledTask] = []
        for idx, pose in enumerate(poses):
            override = {
                "center_m": pose.get("center_m", request["radar"]["center_m"]),
                "look_at_m": pose.get("look_at_m", request["radar"]["look_at_m"]),
            }
            if "tx_rx_baseline_m" in pose:
                override["tx_rx_baseline_m"] = pose["tx_rx_baseline_m"]
            tasks.append(ScheduledTask(task_index=idx, gpu_id=gpu_ids[idx % len(gpu_ids)], radar_override=override))
        return tasks

    def submit_single(self, job_id: str, request: dict[str, Any]) -> None:
        gpu_ids = list(request.get("gpu_ids") or list(self.settings.allowed_gpu_ids))
        self.validate_gpu_ids(gpu_ids)
        tasks = self.expand_tasks(request, gpu_ids)
        self.job_store.create(job_id, request, gpu_ids)
        self.job_store.update_status(
            job_id,
            progress={"total_tasks": len(tasks), "completed_tasks": 0, "failed_tasks": 0},
        )
        self.job_store.append_event(
            job_id,
            {
                "type": "job_queued",
                "gpu_ids": gpu_ids,
                "mode": request.get("mode", "single_pose"),
                "task_count": len(tasks),
            },
        )
        thread = Thread(
            target=self._run_background_guarded,
            args=(job_id, request, tasks),
            daemon=False,
            name=f"radar-job-{job_id}",
        )
        thread.start()

    def _run_background_guarded(self, job_id: str, request: dict[str, Any], tasks: list[ScheduledTask]) -> None:
        try:
            self._run_background(job_id, request, tasks)
        except Exception as exc:
            trace = traceback.format_exc()
            try:
                previous = self.job_store.load_status(job_id)
            except (OSError, ValueError):
                previous = {}
            available_run_ids = [str(item) for item in previous.get("available_run_ids", [])]
            run_ids = {task_run_id(job_id, task.task_index) for task in tasks} - set(available_run_ids)
            self._cleanup_failed_artifacts(job_id, run_ids, remove_campaign=not available_run_ids)
            paths = self.job_store.job_paths(job_id)
            with paths.logs_txt.open("a", encoding="utf-8") as f:
                f.write(f"{type(exc).__name__}: {exc}\n{trace}\n")
            self.job_store.update_status(
                job_id,
                status="failed",
                completed_at_utc=utc_now(),
                progress={
                    "total_tasks": len(tasks),
                    "completed_tasks": len(available_run_ids),
                    "failed_tasks": max(len(tasks) - len(available_run_ids), 1),
                },
                current_tasks=[],
                available_run_ids=available_run_ids,
                result={"campaign_id": job_id, "run_ids": available_run_ids, "partial": True} if available_run_ids else None,
                error=f"{type(exc).__name__}: {exc}\n{trace}",
            )
            self.job_store.append_event(job_id, {"type": "job_failed", "error": f"{type(exc).__name__}: {exc}"})

    def _write_partial_artifacts(self, job_id: str, request: dict[str, Any], results: list[dict[str, Any]]) -> None:
        if not results:
            return
        results = sorted(results, key=lambda item: int(item["result"].get("task_index", 0)))
        campaign_root = self.settings.workbench_output_root / "campaigns" / job_id
        rows = [item["row"] for item in results]
        run_ids = [item["result"]["run_id"] for item in results]
        write_pose_metrics(campaign_root, rows)
        SimulationWorker(self.settings, self.job_store).write_campaign_manifest(
            campaign_root,
            job_id,
            run_ids,
            request,
        )

    def _cleanup_failed_artifacts(self, job_id: str, run_ids: set[str], *, remove_campaign: bool = False) -> None:
        """Remove artifacts from tasks that never produced a complete result."""
        campaign_root = self.settings.workbench_output_root / "campaigns" / job_id
        for run_id in run_ids:
            shutil.rmtree(campaign_root / "runs" / run_id, ignore_errors=True)
            shutil.rmtree(self.settings.web_cache_root / run_id, ignore_errors=True)
        if remove_campaign:
            shutil.rmtree(campaign_root, ignore_errors=True)

    def _run_background(self, job_id: str, request: dict[str, Any], tasks: list[ScheduledTask]) -> None:
        self.job_store.update_status(
            job_id,
            status="running",
            started_at_utc=utc_now(),
            current_tasks=[],
        )
        self.job_store.append_event(
            job_id,
            {"type": "job_running", "task_count": len(tasks), "gpu_ids": sorted({task.gpu_id for task in tasks})},
        )
        by_gpu: dict[int, list[dict[str, Any]]] = {}
        for task in tasks:
            by_gpu.setdefault(task.gpu_id, []).append(
                {
                    "task_index": task.task_index,
                    "radar_override": task.radar_override,
                }
            )

        ctx = mp.get_context("spawn")
        queue: mp.Queue = ctx.Queue()
        procs: list[mp.Process] = []
        for gpu_id, gpu_tasks in by_gpu.items():
            proc = ctx.Process(
                target=_worker_entry,
                args=(self.settings, job_id, request, gpu_id, gpu_tasks, queue),
                daemon=False,
            )
            proc.start()
            procs.append(proc)

        total = len(tasks)
        completed = 0
        failed = 0
        done_workers = 0
        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        active: dict[int, dict[str, Any]] = {}

        while completed + failed < total and not errors:
            try:
                msg = queue.get(timeout=1.0)
            except Empty:
                if all(not proc.is_alive() for proc in procs) and done_workers < len(procs):
                    errors.append({"error": "All GPU workers exited before completing all tasks", "traceback": ""})
                continue

            status = msg.get("status")
            if status == "start":
                active[int(msg["gpu_id"])] = {
                    "gpu_id": msg["gpu_id"],
                    "run_id": msg["run_id"],
                    "task_index": msg["task_index"],
                    "status": "running",
                }
                self.job_store.update_status(job_id, current_tasks=list(active.values()))
            elif status == "ok":
                completed += 1
                results.append(msg["result"])
                active.pop(int(msg["gpu_id"]), None)
                self._write_partial_artifacts(job_id, request, results)
                available_run_ids = [
                    item["result"]["run_id"]
                    for item in sorted(results, key=lambda item: int(item["result"].get("task_index", 0)))
                ]
                self.job_store.update_status(
                    job_id,
                    current_tasks=list(active.values()),
                    progress={"total_tasks": total, "completed_tasks": completed, "failed_tasks": failed},
                    available_run_ids=available_run_ids,
                )
            elif status == "error":
                failed += 1
                errors.append(msg)
                active.pop(int(msg["gpu_id"]), None)
            elif status == "worker_done":
                done_workers += 1

        for proc in procs:
            proc.join(timeout=5)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)

        failed_run_ids = {
            str(item.get("run_id"))
            for item in errors
            if item.get("run_id")
        }
        failed_run_ids.update(
            str(item.get("run_id"))
            for item in active.values()
            if item.get("run_id")
        )
        self._cleanup_failed_artifacts(job_id, failed_run_ids, remove_campaign=bool(errors and not results))

        self._write_partial_artifacts(job_id, request, results)

        if errors:
            error = str(errors[0].get("error", "unknown worker failure"))
            trace = str(errors[0].get("traceback", ""))
            paths = self.job_store.job_paths(job_id)
            with paths.logs_txt.open("a", encoding="utf-8") as f:
                f.write(error)
                f.write("\n")
                f.write(trace)
                f.write("\n")
            self.job_store.update_status(
                job_id,
                status="failed",
                completed_at_utc=utc_now(),
                progress={"total_tasks": total, "completed_tasks": completed, "failed_tasks": max(failed, 1)},
                current_tasks=[],
                available_run_ids=[item["result"]["run_id"] for item in results],
                result={
                    "campaign_id": job_id,
                    "run_ids": [item["result"]["run_id"] for item in results],
                    "partial": True,
                } if results else None,
                error=f"{error}\n{trace}",
            )
            self.job_store.append_event(job_id, {"type": "job_failed", "error": error})
            return

        results = sorted(results, key=lambda item: int(item["result"].get("task_index", 0)))
        run_results = [item["result"] for item in results]
        result = {
            "campaign_id": job_id,
            "output_root": str(self.settings.workbench_output_root / "campaigns" / job_id),
            "run_id": run_results[0]["run_id"],
            "run_ids": [item["run_id"] for item in run_results],
            "run_dirs": [item["run_dir"] for item in run_results],
            "web_caches": [item["web_cache"] for item in run_results],
        }
        self.job_store.update_status(
            job_id,
            status="complete",
            completed_at_utc=utc_now(),
            progress={"total_tasks": total, "completed_tasks": completed, "failed_tasks": 0},
            current_tasks=[],
            available_run_ids=[item["run_id"] for item in run_results],
            result=result,
            error=None,
        )
        self.job_store.append_event(job_id, {"type": "job_complete", "result": result})
