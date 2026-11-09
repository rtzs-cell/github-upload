#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def rebase_experiment(experiment_root: Path) -> int:
    manifest_path = experiment_root / "experiment_manifest.json"
    config_path = experiment_root / "input" / "experiment_config.json"
    scene_config_path = experiment_root / "input" / "scene_config.json"
    if not manifest_path.exists() or not config_path.exists():
        return 0

    manifest = read_json(manifest_path)
    config = read_json(config_path)
    scene = config.get("scene", {})
    relative_scene = scene.get("scene_xml") or manifest.get("files", {}).get("scene_xml")
    if relative_scene:
        scene["scene_xml_path"] = str((experiment_root / relative_scene).resolve())
    manifest["root"] = str(experiment_root.resolve())
    write_json(manifest_path, manifest)
    write_json(config_path, config)
    if scene_config_path.exists():
        write_json(scene_config_path, scene)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebase editable radar experiment paths after migration")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    experiments_root = args.repo.resolve() / "outputs" / "radar_workbench" / "experiments"
    count = 0
    if experiments_root.exists():
        for experiment_root in sorted(experiments_root.iterdir()):
            if experiment_root.is_dir():
                count += rebase_experiment(experiment_root)
    print(f"Rebased {count} editable experiment(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
