from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree


def scene_path_candidates(metadata: dict[str, Any]) -> list[Path]:
    raw = metadata.get("scene_path")
    if not raw:
        return []
    path = Path(str(raw))
    candidates = [path]
    cwd = metadata.get("cwd")
    if not path.is_absolute() and cwd:
        candidates.insert(0, Path(str(cwd)) / path)
    return candidates


def match_shape_id(shape_id: str, object_ids: list[str]) -> str | None:
    candidates = [shape_id]
    for prefix in ("mesh-", "mesh_", "shape-", "shape_"):
        if shape_id.startswith(prefix):
            candidates.append(shape_id[len(prefix):])
    for candidate in candidates:
        if candidate in object_ids:
            return candidate
    normalized = {value.lower().replace("-", "_"): value for value in object_ids}
    for candidate in candidates:
        match = normalized.get(candidate.lower().replace("-", "_"))
        if match:
            return match
    return None


def object_index_map(metadata: dict[str, Any]) -> dict[int, str]:
    objects = metadata.get("scene_geometry", {}).get("objects", {})
    object_ids = list(objects.keys())
    for scene_path in scene_path_candidates(metadata):
        if not scene_path.exists():
            continue
        try:
            root = ElementTree.parse(scene_path).getroot()
        except (OSError, ElementTree.ParseError):
            continue
        mapping: dict[int, str] = {}
        shape_index = 0
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "shape":
                continue
            shape_index += 1
            object_id = match_shape_id(str(element.get("id", "")), object_ids)
            if object_id:
                mapping[shape_index] = object_id
        if mapping:
            return mapping
    return {idx: object_id for idx, object_id in enumerate(object_ids, start=1)}
