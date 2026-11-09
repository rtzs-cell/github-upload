import csv
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import get_settings
from app.core.beamforming import build_beamforming_artifacts
from app.core.mpc_analysis import build_mpc_analysis_artifacts
from app.core.radar_signal import build_fmcw_artifacts
from app.core.result_downloads import artifact_path, build_analysis_bundle, download_catalog
from app.core.history_management import delete_local_run
from app.core.path_statistics import build_result_bundle, write_statistics_artifacts, read_json as read_stats_json
from app.core.web_cache import SCHEMA_VERSION as WEB_CACHE_SCHEMA_VERSION
from app.core.web_cache import build_web_cache, read_json
from app.deps import get_result_loader
from app.paths import ensure_within
from app.schemas import (
    AnalysisArtifactsResponse,
    InteractionsResponse,
    BeamformingResponse,
    DownloadCatalogResponse,
    PathExportRequest,
    PathExportResponse,
    PathStatisticsResponse,
    ResultBundleResponse,
    RunMetadataResponse,
    NameUpdateRequest,
    SceneObjectsResponse,
    SpectrumMetadata,
    TopPathsResponse,
)

router = APIRouter(prefix="/api/results", tags=["results"])
_analysis_locks: dict[str, threading.Lock] = {}
_analysis_locks_guard = threading.Lock()


@router.patch("/{run_id}/name")
def set_result_name(run_id: str, request: NameUpdateRequest) -> dict:
    settings = get_settings()
    local_runs_root = settings.workbench_output_root / "campaigns"
    run_dir = None
    for runs_root in local_runs_root.glob("*/runs"):
        candidate = runs_root / run_id
        if candidate.is_dir() and candidate.name == run_id:
            run_dir = ensure_within(candidate, local_runs_root)
            break
    if run_dir is None:
        loader = get_result_loader()
        try:
            loader.run_dir(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}") from exc
        raise HTTPException(status_code=403, detail="只读基准记录不能改名")
    payload = {
        "display_name": request.name.strip(),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with (run_dir / "display_name.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"run_id": run_id, **payload}


def analysis_lock(run_id: str) -> threading.Lock:
    with _analysis_locks_guard:
        return _analysis_locks.setdefault(run_id, threading.Lock())


def artifact_is_fresh(targets: list[Path], sources: list[Path]) -> bool:
    if not targets or not all(path.exists() for path in targets):
        return False
    source_mtime = max((path.stat().st_mtime for path in sources if path.exists()), default=0.0)
    return min(path.stat().st_mtime for path in targets) >= source_mtime


@router.delete("/{run_id}")
def remove_result(run_id: str) -> dict:
    settings = get_settings()
    try:
        return delete_local_run(settings, run_id)
    except FileNotFoundError as exc:
        loader = get_result_loader()
        try:
            loader.run_dir(run_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown run_id: {run_id}") from exc
        raise HTTPException(status_code=403, detail="只读基准记录不能删除") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def cache_dir_for(run_id: str) -> Path:
    settings = get_settings()
    return ensure_within(settings.web_cache_root / run_id, settings.web_cache_root)


def ensure_cache(run_id: str) -> Path:
    loader = get_result_loader()
    settings = get_settings()
    cache_dir = cache_dir_for(run_id)
    required = [
        cache_dir / "manifest.json",
        cache_dir / "top_paths.json",
        cache_dir / "range_azimuth.json",
        cache_dir / "range_azimuth.bin",
        cache_dir / "range_elevation.json",
        cache_dir / "range_elevation.bin",
    ]
    if all(path.exists() for path in required):
        try:
            manifest = read_json(cache_dir / "manifest.json")
            if manifest.get("schema_version") == WEB_CACHE_SCHEMA_VERSION:
                return cache_dir
        except Exception:
            pass
    try:
        return build_web_cache(loader.run_dir(run_id), settings.web_cache_root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build cache: {exc}") from exc


def selected_paths_data(
    run_id: str,
    top_k: int,
    kind: Literal["all", "specular", "diffuse", "mixed", "unknown"],
    in_fov: bool,
) -> dict:
    cache_dir = ensure_cache(run_id)
    data = read_json(cache_dir / "top_paths.json")
    path_items = data["paths"]
    if in_fov:
        path_items = [item for item in path_items if item.get("in_fov")]
    if kind != "all":
        path_items = [item for item in path_items if item.get("kind") == kind]
    return {
        **data,
        "paths": path_items[:top_k],
        "selection": {
            **data.get("selection", {}),
            "returned_top_k": top_k,
            "kind": kind,
            "in_fov": in_fov,
        },
    }


def safe_export_id(run_id: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id)[:96]
    return f"paths_{timestamp}_{safe_run_id}_{uuid.uuid4().hex[:8]}"


def write_path_summary_csv(path: Path, paths: list[dict]) -> None:
    fieldnames = [
        "path_id",
        "kind",
        "depth",
        "range_m",
        "delay_s",
        "energy",
        "aoa_azimuth_deg",
        "aoa_elevation_deg",
        "in_fov",
        "interaction_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in paths:
            writer.writerow(
                {
                    "path_id": item.get("path_id"),
                    "kind": item.get("kind"),
                    "depth": item.get("depth"),
                    "range_m": item.get("range_m"),
                    "delay_s": item.get("delay_s"),
                    "energy": item.get("energy"),
                    "aoa_azimuth_deg": item.get("aoa_azimuth_deg"),
                    "aoa_elevation_deg": item.get("aoa_elevation_deg"),
                    "in_fov": item.get("in_fov"),
                    "interaction_count": len(item.get("interactions", [])),
                }
            )


@router.get("/{run_id}/metadata", response_model=RunMetadataResponse)
def metadata(run_id: str) -> RunMetadataResponse:
    loader = get_result_loader()
    try:
        return RunMetadataResponse(**loader.load_metadata_response(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc


@router.get("/{run_id}/scene_objects", response_model=SceneObjectsResponse)
def scene_objects(run_id: str) -> SceneObjectsResponse:
    try:
        cache_dir = ensure_cache(run_id)
        data = read_json(cache_dir / "scene_objects.json")
        return SceneObjectsResponse(run_id=run_id, objects=data["objects"])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/paths", response_model=TopPathsResponse)
def paths(
    run_id: str,
    top_k: int = Query(default=500, ge=1, le=5000),
    kind: Literal["all", "specular", "diffuse", "mixed", "unknown"] = "all",
    in_fov: bool = True,
) -> TopPathsResponse:
    try:
        data = selected_paths_data(run_id, top_k, kind, in_fov)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TopPathsResponse(**data)


@router.post("/{run_id}/path_exports", response_model=PathExportResponse)
def save_path_export(run_id: str, request: PathExportRequest) -> PathExportResponse:
    loader = get_result_loader()
    settings = get_settings()
    export_root = settings.workbench_output_root / "path_exports"
    export_root.mkdir(parents=True, exist_ok=True)
    export_id = safe_export_id(run_id)
    export_dir = ensure_within(export_root / export_id, export_root)
    export_dir.mkdir(parents=True, exist_ok=False)
    try:
        path_data = selected_paths_data(run_id, request.top_k, request.kind, request.in_fov)
        metadata_data = loader.load_metadata_response(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc

    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "export_id": export_id,
        "created_at_utc": created_at,
        "run_id": run_id,
        "path_count": len(path_data["paths"]),
        "selection": path_data["selection"],
        "note": request.note,
        "files": {
            "manifest": "manifest.json",
            "paths": "paths.json",
            "path_summary": "path_summary.csv",
            "radar_config": "radar_config.json",
            "run_metadata": "run_metadata.json",
        },
    }
    radar_config = {
        "created_at_utc": created_at,
        "run_id": run_id,
        "draft_config": request.draft_config,
        "source_config": metadata_data["config"],
        "source_metadata": metadata_data["metadata"],
        "source_metrics": metadata_data["metrics"],
    }

    files = {
        "manifest": export_dir / "manifest.json",
        "paths": export_dir / "paths.json",
        "path_summary": export_dir / "path_summary.csv",
        "radar_config": export_dir / "radar_config.json",
        "run_metadata": export_dir / "run_metadata.json",
    }
    for key in ["manifest", "paths", "radar_config", "run_metadata"]:
        payload = {
            "manifest": manifest,
            "paths": path_data,
            "radar_config": radar_config,
            "run_metadata": metadata_data,
        }[key]
        with files[key].open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
    write_path_summary_csv(files["path_summary"], path_data["paths"])

    return PathExportResponse(
        export_id=export_id,
        run_id=run_id,
        root=str(export_dir),
        path_count=len(path_data["paths"]),
        files={key: str(path) for key, path in files.items()},
    )


@router.get("/{run_id}/interactions", response_model=InteractionsResponse)
def interactions(
    run_id: str,
    top_k: int = Query(default=20000, ge=1, le=100000),
    in_fov: bool = True,
) -> InteractionsResponse:
    try:
        cache_dir = ensure_cache(run_id)
        parquet_path = cache_dir / "first_interactions.parquet"
        df = pd.read_parquet(parquet_path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if in_fov and "in_fov" in df.columns:
        df = df[df["in_fov"]]
    df = df.head(top_k)
    return InteractionsResponse(
        run_id=run_id,
        columns=list(df.columns),
        interactions=df.where(pd.notnull(df), None).to_dict(orient="records"),
    )


@router.get("/{run_id}/path_statistics", response_model=PathStatisticsResponse)
def path_statistics(run_id: str) -> PathStatisticsResponse:
    loader = get_result_loader()
    try:
        run_dir = loader.run_dir(run_id)
        files = write_statistics_artifacts(run_dir)
        summary = read_stats_json(Path(files["path_statistics"]))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc
    return PathStatisticsResponse(summary=summary, files=files)


@router.get("/{run_id}/mpc_analysis", response_model=AnalysisArtifactsResponse)
def mpc_analysis(run_id: str) -> AnalysisArtifactsResponse:
    loader = get_result_loader()
    try:
        run_dir = loader.run_dir(run_id)
        summary_path = run_dir / "analysis" / "analysis_gate_mpc_summary.json"
        csv_path = run_dir / "analysis" / "analysis_gate_mpc.csv"
        figure_path = run_dir / "figures" / "analysis_gate_mpc.png"
        panorama_path = run_dir / "figures" / "mpc_panorama.png"
        panorama_array = run_dir / "analysis" / "mpc_panorama.npz"
        sources = [run_dir / name for name in ("paths_summary.npz", "radar_observation.npz", "metrics.json", "config.yaml")]
        with analysis_lock(run_id):
            fresh = artifact_is_fresh([summary_path, csv_path, figure_path, panorama_path, panorama_array], sources)
            summary = read_stats_json(summary_path) if fresh else None
            if not summary or summary.get("schema_version") != "1.2.0":
                result = build_mpc_analysis_artifacts(run_dir)
            else:
                result = {"summary": summary, "files": summary.get("files", {})}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc
    return AnalysisArtifactsResponse(summary=result["summary"], files=result["files"])


@router.get("/{run_id}/beamforming", response_model=BeamformingResponse)
def beamforming(
    run_id: str,
    rx_mode: str | None = None,
    steering_azimuth_deg: float | None = None,
    steering_elevation_deg: float | None = None,
) -> BeamformingResponse:
    loader = get_result_loader()
    override = {
        key: value
        for key, value in {
            "rx_mode": rx_mode,
            "steering_azimuth_deg": steering_azimuth_deg,
            "steering_elevation_deg": steering_elevation_deg,
        }.items()
        if value is not None
    }
    if override:
        raise HTTPException(
            status_code=409,
            detail="Run snapshots are immutable. Change beamforming parameters in the draft and submit a new simulation.",
        )
    try:
        run_dir = loader.run_dir(run_id)
        with analysis_lock(run_id):
            summary_path = run_dir / "analysis" / "beamforming_summary.json"
            if not override and artifact_is_fresh(
                [summary_path, run_dir / "analysis" / "beamformed_observation.npz"],
                [run_dir / "cir.npz", run_dir / "paths_summary.npz", run_dir / "config.yaml"],
            ):
                summary = read_stats_json(summary_path)
                if summary.get("schema_version") == "0.4.0":
                    result = {"summary": summary, "files": summary.get("files", {})}
                else:
                    result = build_beamforming_artifacts(run_dir)
            else:
                result = build_beamforming_artifacts(run_dir)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BeamformingResponse(summary=result["summary"], files=result["files"])


@router.get("/{run_id}/fmcw", response_model=AnalysisArtifactsResponse)
def fmcw(run_id: str) -> AnalysisArtifactsResponse:
    loader = get_result_loader()
    try:
        run_dir = loader.run_dir(run_id)
        with analysis_lock(run_id):
            beam_path = run_dir / "analysis" / "beamformed_observation.npz"
            beam_summary_path = run_dir / "analysis" / "beamforming_summary.json"
            beam_current = False
            if beam_path.exists() and beam_summary_path.exists():
                beam_summary = read_stats_json(beam_summary_path)
                if beam_summary.get("schema_version") == "0.4.0":
                    with np.load(beam_path, allow_pickle=False) as beam_data:
                        beam_current = "beamformed_path_coefficients" in beam_data.files
            if not beam_current:
                build_beamforming_artifacts(run_dir)
            summary_path = run_dir / "analysis" / "fmcw_summary.json"
            if artifact_is_fresh([summary_path], [run_dir / "paths_summary.npz", beam_path, run_dir / "config.yaml"]):
                summary = read_stats_json(summary_path)
                if summary.get("schema_version") == "0.2.0":
                    result = {"summary": summary, "files": summary.get("files", {})}
                else:
                    result = build_fmcw_artifacts(run_dir)
            else:
                result = build_fmcw_artifacts(run_dir)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnalysisArtifactsResponse(summary=result["summary"], files=result["files"])


@router.get("/{run_id}/result_bundle", response_model=ResultBundleResponse)
def result_bundle(run_id: str) -> ResultBundleResponse:
    loader = get_result_loader()
    settings = get_settings()
    try:
        run_dir = loader.run_dir(run_id)
        bundle = build_result_bundle(run_dir, settings.workbench_output_root / "result_bundles")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc
    return ResultBundleResponse(run_id=run_id, bundle_path=str(bundle))


@router.get("/{run_id}/downloads", response_model=DownloadCatalogResponse)
def downloads(run_id: str) -> DownloadCatalogResponse:
    loader = get_result_loader()
    try:
        run_dir = loader.run_dir(run_id)
        return DownloadCatalogResponse(run_id=run_id, artifacts=download_catalog(run_dir, run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}/downloads/{artifact_id}")
def download_artifact(run_id: str, artifact_id: str) -> FileResponse:
    loader = get_result_loader()
    settings = get_settings()
    try:
        run_dir = loader.run_dir(run_id)
        if artifact_id == "analysis_bundle":
            path = build_analysis_bundle(run_dir, settings.workbench_output_root / "result_bundles")
        else:
            path = artifact_path(run_dir, artifact_id)
        if not path.exists():
            raise FileNotFoundError(path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing artifact: {exc}") from exc
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@router.get("/{run_id}/result_bundle.zip")
def download_result_bundle(run_id: str) -> FileResponse:
    loader = get_result_loader()
    settings = get_settings()
    try:
        run_dir = loader.run_dir(run_id)
        bundle = build_result_bundle(run_dir, settings.workbench_output_root / "result_bundles")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Missing run file: {exc}") from exc
    return FileResponse(bundle, media_type="application/zip", filename=bundle.name)


def spectrum_metadata(run_id: str, kind: Literal["range_azimuth", "range_elevation"]) -> SpectrumMetadata:
    cache_dir = ensure_cache(run_id)
    data = read_json(cache_dir / f"{kind}.json")
    return SpectrumMetadata(
        run_id=run_id,
        kind=kind,
        dtype=data["dtype"],
        shape=data["shape"],
        layout=data["layout"],
        array_url=f"/api/results/{run_id}/{kind}/array",
        range_edges_m=data["range_edges_m"],
        angle_edges_deg=data["angle_edges_deg"],
        angle_label=data["angle_label"],
        scale=data["scale"],
        recommended_display=data["recommended_display"],
    )


@router.get("/{run_id}/range_azimuth", response_model=SpectrumMetadata)
def range_azimuth(run_id: str) -> SpectrumMetadata:
    return spectrum_metadata(run_id, "range_azimuth")


@router.get("/{run_id}/range_elevation", response_model=SpectrumMetadata)
def range_elevation(run_id: str) -> SpectrumMetadata:
    return spectrum_metadata(run_id, "range_elevation")


@router.get("/{run_id}/{kind}/array")
def spectrum_array(run_id: str, kind: Literal["range_azimuth", "range_elevation"]) -> FileResponse:
    cache_dir = ensure_cache(run_id)
    path = ensure_within(cache_dir / f"{kind}.bin", cache_dir)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Spectrum array not found")
    return FileResponse(path, media_type="application/octet-stream")


@router.get("/{run_id}/figures/{figure_name}")
def figure(run_id: str, figure_name: str) -> FileResponse:
    loader = get_result_loader()
    try:
        path = loader.figure_path(run_id, figure_name)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path)
