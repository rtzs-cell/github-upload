from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from app.config import Settings
from app.core.campaign_registry import CampaignRegistry
from app.paths import ensure_within


class ResultLoader:
    def __init__(self, settings: Settings, registry: CampaignRegistry):
        self.settings = settings
        self.registry = registry

    def run_index(self) -> dict[str, Path]:
        return self.registry.build_run_index()

    def run_dir(self, run_id: str) -> Path:
        try:
            run_dir = self.run_index()[run_id]
        except KeyError as exc:
            raise KeyError(f"Unknown run_id: {run_id}") from exc
        resolved = run_dir.resolve()
        existing_root = self.settings.existing_campaign_root.resolve()
        workbench_campaigns = (self.settings.workbench_output_root / "campaigns").resolve()
        if resolved == existing_root or existing_root in resolved.parents:
            return resolved
        return ensure_within(resolved, workbench_campaigns)

    def load_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def load_config(self, run_dir: Path) -> dict[str, Any]:
        path = run_dir / "config.yaml"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}

    def load_metadata_response(self, run_id: str) -> dict[str, Any]:
        run_dir = self.run_dir(run_id)
        metadata = self.load_json(run_dir / "metadata.json")
        metrics = self.load_json(run_dir / "metrics.json")
        config = self.load_config(run_dir)
        cache_dir = self.settings.web_cache_root / run_id
        return {
            "run_id": run_id,
            "config": config,
            "metadata": metadata,
            "metrics": metrics,
            "available_artifacts": {
                "top_paths": (cache_dir / "top_paths.json").exists(),
                "first_interactions": (cache_dir / "first_interactions.parquet").exists(),
                "range_azimuth": (cache_dir / "range_azimuth.bin").exists(),
                "range_elevation": (cache_dir / "range_elevation.bin").exists(),
                "cir": False,
            },
        }

    def scene_objects(self, run_id: str) -> list[dict[str, Any]]:
        run_dir = self.run_dir(run_id)
        metadata = self.load_json(run_dir / "metadata.json")
        objects = metadata.get("scene_geometry", {}).get("objects", {})
        result = []
        for object_id, obj in objects.items():
            item = {"object_id": object_id}
            item.update(obj)
            result.append(item)
        return result

    def figure_path(self, run_id: str, figure_name: str) -> Path:
        run_dir = self.run_dir(run_id)
        path = ensure_within(run_dir / "figures" / figure_name, run_dir)
        if not path.exists():
            raise FileNotFoundError(path)
        return path
