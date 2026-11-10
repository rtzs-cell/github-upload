from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import get_settings
from app.core.scene_imports import fetch_osm_scene_bbox_import, fetch_osm_scene_import, store_scene_import
from app.core.two_building_scene import (
    create_experiment,
    default_two_building_config,
    list_experiments,
    load_experiment,
    config_for_scene_preset,
    rename_experiment,
    scene_presets,
    update_experiment,
    experiment_model_path,
    store_experiment_model,
)
from app.core.history_management import delete_experiment
from app.schemas import ExperimentCreateRequest, ExperimentListResponse, ExperimentResponse, ExperimentSummary, ExperimentUpdateRequest, NameUpdateRequest, OsmBboxFetchRequest, OsmFetchRequest


router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("/templates/two_buildings")
def two_building_template() -> dict:
    return default_two_building_config()


@router.get("/presets")
def presets() -> dict:
    return scene_presets()


@router.get("/presets/{preset_id}")
def preset(preset_id: str) -> dict:
    try:
        return config_for_scene_preset(preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=ExperimentListResponse)
def experiments() -> ExperimentListResponse:
    settings = get_settings()
    return ExperimentListResponse(
        experiments=[ExperimentSummary(**item) for item in list_experiments(settings.workbench_output_root)]
    )


@router.post("", response_model=ExperimentResponse)
def create(request: ExperimentCreateRequest) -> ExperimentResponse:
    settings = get_settings()
    try:
        result = create_experiment(settings.workbench_output_root, request.config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExperimentResponse(manifest=ExperimentSummary(**result["manifest"]), config=result["config"])


@router.get("/{experiment_id}", response_model=ExperimentResponse)
def get_experiment(experiment_id: str) -> ExperimentResponse:
    settings = get_settings()
    try:
        result = load_experiment(settings.workbench_output_root, experiment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    return ExperimentResponse(manifest=ExperimentSummary(**result["manifest"]), config=result["config"])


@router.post("/{experiment_id}/models")
async def upload_model(experiment_id: str, request: Request, filename: str) -> dict:
    settings = get_settings()
    content_length = int(request.headers.get("content-length", "0") or 0)
    if content_length > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Model file exceeds the 100 MB limit")
    data = await request.body()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Model file exceeds the 100 MB limit")
    try:
        return store_experiment_model(settings.workbench_output_root, experiment_id, filename, data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experiment_id}/scene-imports")
async def upload_scene_import(experiment_id: str, request: Request, filename: str) -> dict:
    settings = get_settings()
    content_length = int(request.headers.get("content-length", "0") or 0)
    if content_length > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Scene file exceeds the 50 MB limit")
    data = await request.body()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Scene file exceeds the 50 MB limit")
    try:
        return store_scene_import(settings.workbench_output_root, experiment_id, filename, data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experiment_id}/scene-fetch/osm")
def fetch_osm_scene(experiment_id: str, request: OsmFetchRequest) -> dict:
    settings = get_settings()
    try:
        return fetch_osm_scene_import(
            settings.workbench_output_root,
            experiment_id,
            request.latitude,
            request.longitude,
            request.radius_km,
            settings.overpass_url,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{experiment_id}/scene-fetch/osm-bbox")
def fetch_osm_scene_bbox(experiment_id: str, request: OsmBboxFetchRequest) -> dict:
    settings = get_settings()
    try:
        return fetch_osm_scene_bbox_import(
            settings.workbench_output_root,
            experiment_id,
            request.south,
            request.west,
            request.north,
            request.east,
            settings.overpass_url,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{experiment_id}/models/{asset_name}")
def model_asset(experiment_id: str, asset_name: str) -> FileResponse:
    settings = get_settings()
    try:
        path = experiment_model_path(settings.workbench_output_root, experiment_id, asset_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model asset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    media_type = "text/plain" if path.suffix.lower() == ".obj" else "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.put("/{experiment_id}", response_model=ExperimentResponse)
def save_experiment(experiment_id: str, request: ExperimentUpdateRequest) -> ExperimentResponse:
    settings = get_settings()
    try:
        result = update_experiment(settings.workbench_output_root, experiment_id, request.config)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExperimentResponse(manifest=ExperimentSummary(**result["manifest"]), config=result["config"])


@router.patch("/{experiment_id}/name", response_model=ExperimentResponse)
def set_experiment_name(experiment_id: str, request: NameUpdateRequest) -> ExperimentResponse:
    settings = get_settings()
    try:
        result = rename_experiment(settings.workbench_output_root, experiment_id, request.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    return ExperimentResponse(manifest=ExperimentSummary(**result["manifest"]), config=result["config"])


@router.delete("/{experiment_id}")
def remove_experiment(experiment_id: str) -> dict:
    settings = get_settings()
    try:
        return delete_experiment(settings, experiment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown experiment_id: {experiment_id}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid experiment_id") from exc
