from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

from app.core.two_building_scene import safe_id


SUPPORTED_SCENE_IMPORT_EXTENSIONS = {".osm", ".xml", ".geojson", ".json"}
EARTH_METERS_PER_DEGREE_LAT = 110_540.0
EARTH_METERS_PER_DEGREE_LON = 111_320.0


def _tag_value(tags: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = tags.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _numeric_tag(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", "."))
    if not match:
        return None
    try:
        result = float(match.group(0))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _building_height(tags: dict[str, Any]) -> float:
    height = _numeric_tag(_tag_value(tags, "height", "building:height"))
    if height is not None and height > 0:
        return max(height, 2.5)
    levels = _numeric_tag(_tag_value(tags, "building:levels", "levels"))
    if levels is not None and levels > 0:
        return max(levels * 3.2, 2.5)
    return 12.0


def _material(tags: dict[str, Any]) -> str:
    value = (_tag_value(tags, "building:material", "material") or "").lower()
    if "glass" in value:
        return "glass"
    if "brick" in value or "masonry" in value:
        return "brick"
    if "metal" in value or "steel" in value:
        return "metal"
    if "wood" in value or "timber" in value:
        return "wood"
    if "stone" in value or "marble" in value:
        return "marble"
    return "concrete"


def _project(lat: float, lon: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    scale_lon = EARTH_METERS_PER_DEGREE_LON * math.cos(math.radians(origin_lat))
    return (
        (lon - origin_lon) * scale_lon,
        (lat - origin_lat) * EARTH_METERS_PER_DEGREE_LAT,
    )


def _clean_polygon(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    cleaned: list[tuple[float, float]] = []
    for point in points:
        if not all(math.isfinite(value) for value in point):
            continue
        if not cleaned or point != cleaned[-1]:
            cleaned.append(point)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned


def _building_from_polygon(
    polygon: list[tuple[float, float]],
    tags: dict[str, Any],
    source_type: str,
    source_id: str,
    source_key: str,
    origin_lat: float,
    origin_lon: float,
    index: int,
) -> dict[str, Any] | None:
    polygon = _clean_polygon(polygon)
    if len(polygon) < 3:
        return None
    local = [_project(point[0], point[1], origin_lat, origin_lon) for point in polygon]
    min_x = min(point[0] for point in local)
    max_x = max(point[0] for point in local)
    min_y = min(point[1] for point in local)
    max_y = max(point[1] for point in local)
    size_x = max_x - min_x
    size_y = max_y - min_y
    if size_x < 0.5 or size_y < 0.5:
        return None
    building_id = safe_id(f"{source_key}_{source_type}_{source_id or index}")
    label = _tag_value(tags, "name", "addr:housenumber", "building") or f"OSM Building {index}"
    footprint = [[round(point[0] - (min_x + max_x) / 2.0, 3), round(point[1] - (min_y + max_y) / 2.0, 3)] for point in local]
    height = _building_height(tags)
    return {
        "id": building_id,
        "name": label[:120],
        "center_m": [round((min_x + max_x) / 2.0, 3), round((min_y + max_y) / 2.0, 3), round(height / 2.0, 3)],
        "size_m": [round(size_x, 3), round(size_y, 3), round(height, 3)],
        "rotation_deg": [0.0, 0.0, 0.0],
        "material": _material(tags),
        "geometry_kind": "box",
        "footprint_m": footprint,
        "source": {
            "type": source_type,
            "id": source_id,
            "file_key": source_key,
            "tags": {
                key: str(value)
                for key, value in tags.items()
                if key in {"building", "building:levels", "height", "name", "addr:housenumber", "material", "building:material"}
            },
        },
    }


def _finish_import(
    polygons: list[tuple[list[tuple[float, float]], dict[str, Any], str]],
    source_type: str,
    source_key: str,
    warnings: list[str],
) -> dict[str, Any]:
    if not polygons:
        raise ValueError("No building polygons found")
    all_points = [point for polygon, _, _ in polygons for point in polygon]
    origin_lat = sum(point[0] for point in all_points) / len(all_points)
    origin_lon = sum(point[1] for point in all_points) / len(all_points)
    buildings: list[dict[str, Any]] = []
    for index, (polygon, tags, source_id) in enumerate(polygons, start=1):
        building = _building_from_polygon(
            polygon,
            tags,
            source_type,
            source_id,
            source_key,
            origin_lat,
            origin_lon,
            index,
        )
        if building:
            buildings.append(building)
    if not buildings:
        raise ValueError("Building polygons are too small to create simulation geometry")
    return {
        "source_type": source_type,
        "source_key": source_key,
        "origin": {"latitude": origin_lat, "longitude": origin_lon},
        "buildings": buildings,
        "object_count": len(buildings),
        "warnings": warnings,
    }


def _parse_osm_xml(text: str, source_key: str) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValueError(f"OSM XML parse failed: {exc}") from exc
    nodes: dict[str, tuple[float, float]] = {}
    for element in root:
        if element.tag.rsplit("}", 1)[-1] != "node":
            continue
        node_id = str(element.get("id", ""))
        try:
            nodes[node_id] = (float(element.get("lat", "")), float(element.get("lon", "")))
        except (TypeError, ValueError):
            continue
    polygons: list[tuple[list[tuple[float, float]], dict[str, Any], str]] = []
    warnings: list[str] = []
    for element in root:
        if element.tag.rsplit("}", 1)[-1] != "way":
            continue
        tags = {
            str(tag.get("k")): str(tag.get("v"))
            for tag in element
            if tag.tag.rsplit("}", 1)[-1] == "tag" and tag.get("k")
        }
        if not _tag_value(tags, "building", "building:part"):
            continue
        refs = [
            str(child.get("ref"))
            for child in element
            if child.tag.rsplit("}", 1)[-1] == "nd" and child.get("ref")
        ]
        polygon = [nodes[ref] for ref in refs if ref in nodes]
        if len(polygon) < 3:
            warnings.append(f"way/{element.get('id', '')} has insufficient nodes and was skipped")
            continue
        polygons.append((polygon, tags, str(element.get("id", ""))))
    return _finish_import(polygons, "osm", source_key, warnings)


def _parse_overpass_json(payload: dict[str, Any], source_key: str) -> dict[str, Any]:
    nodes: dict[str, tuple[float, float]] = {}
    for item in payload.get("elements", []):
        if item.get("type") == "node" and item.get("lat") is not None and item.get("lon") is not None:
            nodes[str(item.get("id"))] = (float(item["lat"]), float(item["lon"]))
    polygons: list[tuple[list[tuple[float, float]], dict[str, Any], str]] = []
    warnings: list[str] = []
    for item in payload.get("elements", []):
        if item.get("type") != "way":
            continue
        tags = {str(key): str(value) for key, value in (item.get("tags") or {}).items()}
        if not _tag_value(tags, "building", "building:part"):
            continue
        geometry = item.get("geometry")
        if isinstance(geometry, list):
            polygon = [
                (float(point["lat"]), float(point["lon"]))
                for point in geometry
                if point.get("lat") is not None and point.get("lon") is not None
            ]
        else:
            polygon = [nodes[ref] for ref in item.get("nodes", []) if str(ref) in nodes]
        if len(polygon) < 3:
            warnings.append(f"way/{item.get('id', '')} has insufficient nodes and was skipped")
            continue
        polygons.append((polygon, tags, str(item.get("id", ""))))
    return _finish_import(polygons, "osm", source_key, warnings)


def _geojson_polygons(geometry: dict[str, Any]) -> list[list[tuple[float, float]]]:
    if geometry.get("type") == "Polygon":
        return [
            [(float(point[1]), float(point[0])) for point in ring if len(point) >= 2]
            for ring in (geometry.get("coordinates") or [])[:1]
        ]
    if geometry.get("type") == "MultiPolygon":
        return [
            [(float(point[1]), float(point[0])) for point in polygon[0] if len(point) >= 2]
            for polygon in (geometry.get("coordinates") or [])
            if polygon
        ]
    return []


def _parse_geojson(payload: dict[str, Any], source_key: str) -> dict[str, Any]:
    if payload.get("type") in {"Polygon", "MultiPolygon"}:
        features = [{"type": "Feature", "geometry": payload, "properties": {}}]
    else:
        features = payload.get("features") if payload.get("type") == "FeatureCollection" else [payload]
    polygons: list[tuple[list[tuple[float, float]], dict[str, Any], str]] = []
    warnings: list[str] = []
    for index, feature in enumerate(features or [], start=1):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry") or {}
        properties = {str(key): value for key, value in (feature.get("properties") or {}).items()}
        tags = {key: str(value) for key, value in properties.items() if value is not None}
        if not (_tag_value(tags, "building", "building:part") or _tag_value(tags, "name") or geometry.get("type") in {"Polygon", "MultiPolygon"}):
            continue
        for part_index, polygon in enumerate(_geojson_polygons(geometry), start=1):
            if len(polygon) < 3:
                warnings.append(f"feature/{index} has insufficient nodes and was skipped")
                continue
            polygons.append((polygon, tags, str(feature.get("id") or f"{index}_{part_index}")))
    return _finish_import(polygons, "geojson", source_key, warnings)


def parse_scene_import(filename: str, data: bytes) -> dict[str, Any]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_SCENE_IMPORT_EXTENSIONS:
        raise ValueError("Only OSM XML, Overpass JSON and GeoJSON scene files are supported")
    if not data:
        raise ValueError("Scene file is empty")
    source_key = f"import_{uuid4().hex[:10]}"
    if extension in {".osm", ".xml"} or data.lstrip().startswith(b"<"):
        return _parse_osm_xml(data.decode("utf-8-sig"), source_key)
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Scene JSON parse failed: {exc}") from exc
    if isinstance(payload, dict) and isinstance(payload.get("elements"), list):
        return _parse_overpass_json(payload, source_key)
    if isinstance(payload, dict) and (
        payload.get("type") == "FeatureCollection" or payload.get("type") in {"Feature", "Polygon", "MultiPolygon"}
    ):
        return _parse_geojson(payload, source_key)
    raise ValueError("JSON scene must be an Overpass elements document or GeoJSON FeatureCollection")


def store_scene_import(root: Path, experiment_id: str, filename: str, data: bytes) -> dict[str, Any]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_SCENE_IMPORT_EXTENSIONS:
        raise ValueError("Only .osm, .xml, .geojson or .json files are supported")
    result = parse_scene_import(filename, data)
    from app.core.two_building_scene import load_experiment

    current = load_experiment(root, experiment_id)
    exp_root = Path(current["manifest"]["root"])
    asset_dir = exp_root / "scene" / "imports"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_path = asset_dir / f"{result['source_key']}{extension}"
    asset_path.write_bytes(data)
    result["original_filename"] = Path(filename).name
    result["source_path"] = str(asset_path.relative_to(exp_root))
    for building in result["buildings"]:
        building["source"]["path"] = result["source_path"]
    return result
