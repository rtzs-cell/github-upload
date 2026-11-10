from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = "0.2.0"


MATERIAL_COLORS = {
    "concrete": "0.539479 0.539479 0.539480",
    "glass": "0.212230 0.564711 0.799103",
    "brick": "0.603827 0.090842 0.049707",
    "marble": "0.701101 0.644479 0.485150",
    "wood": "0.508881 0.168269 0.059511",
    "metal": "0.420000 0.430000 0.440000",
}
MATERIAL_PRESETS = {
    "concrete": {"label": "混凝土", "description": "常见建筑主体与地面"},
    "brick": {"label": "砖墙", "description": "砖砌外墙"},
    "glass": {"label": "玻璃", "description": "建筑玻璃幕墙"},
    "marble": {"label": "石材", "description": "致密石材表面"},
    "wood": {"label": "木材", "description": "木质结构或饰面"},
    "metal": {"label": "金属", "description": "高反射金属表面"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_two_building_config() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": "未命名实验方案",
        "scene": {
            "kind": "parametric_two_buildings",
            "ground": {
                "center_m": [450.0, 0.0, -0.05],
                "size_m": [1000.0, 500.0, 0.1],
                "material": "concrete",
            },
            "buildings": [
                {
                    "id": "building_A",
                    "name": "建筑 A",
                    "center_m": [430.0, -35.0, 30.0],
                    "size_m": [45.0, 30.0, 60.0],
                    "rotation_deg": [0.0, 0.0, 0.0],
                    "material": "concrete",
                },
                {
                    "id": "building_B",
                    "name": "建筑 B",
                    "center_m": [480.0, 45.0, 50.0],
                    "size_m": [55.0, 35.0, 100.0],
                    "rotation_deg": [0.0, 0.0, 0.0],
                    "material": "concrete",
                },
            ],
        },
        "radar": {
            "center_m": [0.0, 0.0, 10.0],
            "tx_rx_baseline_m": 0.1,
            "boresight_target": "building_centroid",
            "boresight_elevation_deg": None,
            "azimuth_beamwidth_deg": 120.0,
            "elevation_beamwidth_deg": 40.0,
            "range_max_m": 900.0,
        },
        "waveform": {
            "frequency_hz": 28_000_000_000.0,
            "bandwidth_hz": 1_000_000_000.0,
            "tx_power_dbm": 30.0,
            "chirp_duration_s": 50e-6,
            "idle_time_s": 10e-6,
            "num_chirps": 32,
            "adc_samples": 0,
        },
        "arrays": {
            "tx": {
                "num_rows": 8,
                "num_cols": 8,
                "vertical_spacing": 0.5,
                "horizontal_spacing": 0.5,
                "pattern": "radar_array",
                "polarization": "V",
                "gain_grid_json": None,
                "element_pattern": "tr38901",
                "element_gain_grid_json": None,
            },
            "rx": {
                "num_rows": 16,
                "num_cols": 16,
                "vertical_spacing": 0.5,
                "horizontal_spacing": 0.5,
                "pattern": "iso",
                "polarization": "V",
                "gain_grid_json": None,
            },
        },
        "beamforming": {
            "tx_mode": "embedded_sionna_pattern",
            "tx_steering_azimuth_deg": 0.0,
            "tx_steering_elevation_deg": 0.0,
            "tx_taper": "uniform",
            "tx_weight_mode": "steering_vector",
            "tx_custom_weights_json": None,
            "rx_mode": "steering_vector",
            "steering_azimuth_deg": 0.0,
            "steering_elevation_deg": 0.0,
            "rx_steering_azimuth_deg": 0.0,
            "rx_steering_elevation_deg": 0.0,
            "normalization": "unit_norm",
        },
        "receiver": {
            "noise_figure_db": 8.0,
            "temperature_k": 290.0,
        },
        "radar_processing": {
            "cfar_pfa": 1e-5,
            "max_synthesis_paths": 256,
            "cir_noise": {
                "enabled": False,
                "snr_db": 20.0,
                "seed": 1001,
            },
        },
        "propagation": {
            "max_depth": 2,
            "los": False,
            "specular_reflection": True,
            "diffuse_reflection": True,
            "refraction": False,
            "diffraction": False,
            "edge_diffraction": False,
        },
        "scattering": {
            "enabled": True,
            "coefficient": 0.5,
            "pattern": "backscattering",
            "alpha_r": 20,
            "alpha_i": 20,
            "lambda_": 0.3,
        },
        "solver": {
            "samples_per_src": 500_000,
            "max_num_paths_per_src": 1_000_000,
            "synthetic_array": True,
            "seed": 501,
            "gpu_ids": [0, 1, 2, 3],
            "initial_ray_sampling": {"mode": "full_sphere"},
        },
        "analysis_gate": {
            "azimuth_width_deg": 120.0,
            "elevation_min_deg": 0.0,
            "elevation_max_deg": 40.0,
            "range_max_m": 900.0,
            "min_path_power_db": None,
        },
    }


def scene_presets() -> dict[str, Any]:
    return {
        "materials": MATERIAL_PRESETS,
        "scenes": [
            {"id": "empty", "label": "空白场景", "description": "仅包含地面，从零添加建筑"},
            {"id": "two_buildings", "label": "双建筑", "description": "两栋不同尺寸的建筑"},
            {"id": "street_canyon", "label": "街谷", "description": "道路两侧连续建筑"},
        ],
    }


def config_for_scene_preset(preset_id: str) -> dict[str, Any]:
    config = default_two_building_config()
    config["name"] = f"未命名实验方案 · {datetime.now(timezone.utc).strftime('%m月%d日 %H:%M')}"
    config["scene"]["kind"] = "parametric_buildings"
    if preset_id == "empty":
        config["scene"]["buildings"] = []
    elif preset_id == "street_canyon":
        config["scene"]["buildings"] = [
            {"id": "west_1", "name": "西侧建筑 1", "center_m": [220.0, -42.0, 25.0], "size_m": [70.0, 30.0, 50.0], "material": "brick"},
            {"id": "west_2", "name": "西侧建筑 2", "center_m": [310.0, -42.0, 35.0], "size_m": [80.0, 30.0, 70.0], "material": "concrete"},
            {"id": "east_1", "name": "东侧建筑 1", "center_m": [220.0, 42.0, 30.0], "size_m": [70.0, 30.0, 60.0], "material": "glass"},
            {"id": "east_2", "name": "东侧建筑 2", "center_m": [310.0, 42.0, 25.0], "size_m": [80.0, 30.0, 50.0], "material": "concrete"},
        ]
        config["scene"]["ground"] = {"center_m": [250.0, 0.0, -0.05], "size_m": [700.0, 180.0, 0.1], "material": "concrete"}
    elif preset_id != "two_buildings":
        raise ValueError(f"Unknown scene preset: {preset_id}")
    return config


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "object"


def rotation_matrix(rotation_deg: list[float] | None) -> list[list[float]]:
    rx, ry, rz = [math.radians(float(v)) for v in (rotation_deg or [0.0, 0.0, 0.0])]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ]


def transform_point(matrix: list[list[float]], point: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(sum(matrix[row][col] * point[col] for col in range(3)) for row in range(3))


def box_vertices(
    center_m: list[float],
    size_m: list[float],
    rotation_deg: list[float] | None = None,
) -> list[tuple[float, float, float]]:
    cx, cy, cz = [float(v) for v in center_m]
    sx, sy, sz = [float(v) / 2.0 for v in size_m]
    local = [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]
    matrix = rotation_matrix(rotation_deg)
    return [(x + cx, y + cy, z + cz) for x, y, z in (transform_point(matrix, point) for point in local)]


def write_box_ply(path: Path, center_m: list[float], size_m: list[float], rotation_deg: list[float] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    vertices = box_vertices(center_m, size_m, rotation_deg)
    faces = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 6, 5),
        (4, 7, 6),
        (0, 4, 5),
        (0, 5, 1),
        (1, 5, 6),
        (1, 6, 2),
        (2, 6, 7),
        (2, 7, 3),
        (3, 7, 4),
        (3, 4, 0),
    ]
    with path.open("w", encoding="ascii") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(vertices)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write(f"element face {len(faces)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for x, y, z in vertices:
            f.write(f"{x:.9f} {y:.9f} {z:.9f}\n")
        for face in faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")


def normalize_footprint_points(footprint_m: Any, size_m: list[float]) -> list[tuple[float, float]]:
    if not isinstance(footprint_m, list):
        raise ValueError("Extruded footprint must be a list of points")
    points: list[tuple[float, float]] = []
    for point in footprint_m:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        x, y = float(point[0]), float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        candidate = (x, y)
        if not points or candidate != points[-1]:
            points.append(candidate)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise ValueError("Extruded footprint requires at least three points")
    changed = True
    while changed and len(points) >= 3:
        changed = False
        filtered: list[tuple[float, float]] = []
        for index, point in enumerate(points):
            previous = points[index - 1]
            following = points[(index + 1) % len(points)]
            if abs(_polygon_cross(previous, point, following)) <= 1e-9:
                changed = True
                continue
            filtered.append(point)
        if len(filtered) >= 3:
            points = filtered
    if len(points) < 3:
        raise ValueError("Extruded footprint is collinear")
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    width = max_x - min_x
    depth = max_y - min_y
    if width <= 1e-8 or depth <= 1e-8:
        raise ValueError("Extruded footprint has zero planar extent")
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    scale_x = float(size_m[0]) / width
    scale_y = float(size_m[1]) / depth
    return [
        ((x - center_x) * scale_x, (y - center_y) * scale_y)
        for x, y in points
    ]


def _polygon_cross(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])


def _polygon_area(points: list[tuple[float, float]]) -> float:
    return sum(
        points[index][0] * points[(index + 1) % len(points)][1]
        - points[(index + 1) % len(points)][0] * points[index][1]
        for index in range(len(points))
    ) / 2.0


def _point_in_triangle(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> bool:
    crosses = (
        _polygon_cross(a, b, point),
        _polygon_cross(b, c, point),
        _polygon_cross(c, a, point),
    )
    epsilon = 1e-9
    return min(crosses) >= -epsilon


def triangulate_polygon(points: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    if len(points) < 3 or abs(_polygon_area(points)) <= 1e-8:
        raise ValueError("Footprint polygon is degenerate")
    indices = list(range(len(points)))
    if _polygon_area(points) < 0:
        indices.reverse()
    triangles: list[tuple[int, int, int]] = []
    guard = 0
    while len(indices) > 3:
        ear_found = False
        for position in range(len(indices)):
            previous = indices[position - 1]
            current = indices[position]
            following = indices[(position + 1) % len(indices)]
            if _polygon_cross(points[previous], points[current], points[following]) <= 1e-9:
                continue
            if any(
                index not in {previous, current, following}
                and _point_in_triangle(points[index], points[previous], points[current], points[following])
                for index in indices
            ):
                continue
            triangles.append((previous, current, following))
            del indices[position]
            ear_found = True
            break
        guard += 1
        if not ear_found or guard > len(points) * len(points):
            raise ValueError("Footprint polygon is self-intersecting or cannot be triangulated")
    triangles.append((indices[0], indices[1], indices[2]))
    return triangles


def write_extruded_polygon_ply(
    path: Path,
    footprint_m: Any,
    center_m: list[float],
    size_m: list[float],
    rotation_deg: list[float] | None = None,
) -> None:
    points = normalize_footprint_points(footprint_m, size_m)
    triangles = triangulate_polygon(points)
    height = float(size_m[2])
    local_vertices = [(x, y, -height / 2.0) for x, y in points]
    local_vertices += [(x, y, height / 2.0) for x, y in points]
    matrix = rotation_matrix(rotation_deg)
    vertices = [
        tuple(center_m[index] + transformed[index] for index in range(3))
        for transformed in (transform_point(matrix, point) for point in local_vertices)
    ]
    point_count = len(points)
    faces = [(b + point_count, a + point_count, c + point_count) for a, b, c in triangles]
    faces += [(a, c, b) for a, b, c in triangles]
    for index in range(point_count):
        following = (index + 1) % point_count
        faces.extend([
            (index, following, following + point_count),
            (index, following + point_count, index + point_count),
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as file:
        file.write("ply\n")
        file.write("format ascii 1.0\n")
        file.write(f"element vertex {len(vertices)}\n")
        file.write("property float x\n")
        file.write("property float y\n")
        file.write("property float z\n")
        file.write(f"element face {len(faces)}\n")
        file.write("property list uchar int vertex_indices\n")
        file.write("end_header\n")
        for x, y, z in vertices:
            file.write(f"{x:.9f} {y:.9f} {z:.9f}\n")
        for face in faces:
            file.write(f"3 {face[0]} {face[1]} {face[2]}\n")


def scene_shapes(config: dict[str, Any]) -> list[dict[str, Any]]:
    shapes = []
    ground = config["scene"].get("ground")
    if ground:
        shapes.append(
            {
                "id": "floor",
                "center_m": ground["center_m"],
                "size_m": ground["size_m"],
                "material": ground.get("material", "concrete"),
                "rotation_deg": ground.get("rotation_deg", [0.0, 0.0, 0.0]),
                "geometry_kind": "box",
            }
        )
    shapes.extend(config["scene"].get("buildings", []))
    return shapes


def write_scene_xml(path: Path, shapes: list[dict[str, Any]]) -> None:
    used_materials = sorted({str(shape.get("material", "concrete")) for shape in shapes})
    with path.open("w", encoding="utf-8") as f:
        f.write('<scene version="2.1.0">\n')
        f.write('  <integrator type="path">\n')
        f.write('    <integer name="max_depth" value="12"/>\n')
        f.write("  </integrator>\n")
        f.write('  <emitter type="constant" id="World">\n')
        f.write('    <rgb value="1.000000 1.000000 1.000000" name="radiance"/>\n')
        f.write("  </emitter>\n")
        for material in used_materials:
            itu_name = material if material.startswith("itu_") else f"itu_{material}"
            color = MATERIAL_COLORS.get(material.replace("itu_", ""), MATERIAL_COLORS["concrete"])
            f.write(f'  <bsdf type="twosided" id="mat-{itu_name}">\n')
            f.write('    <bsdf type="diffuse">\n')
            f.write(f'      <rgb value="{color}" name="reflectance"/>\n')
            f.write("    </bsdf>\n")
            f.write("  </bsdf>\n")
        for shape in shapes:
            object_id = safe_id(str(shape["id"]))
            material = str(shape.get("material", "concrete"))
            itu_name = material if material.startswith("itu_") else f"itu_{material}"
            mesh_type = str(shape.get("mesh_type", "ply"))
            mesh_filename = str(shape.get("mesh_filename", f"{object_id}.ply"))
            f.write(f'  <shape type="{mesh_type}" id="mesh-{object_id}">\n')
            f.write(f'    <string name="filename" value="meshes/{mesh_filename}"/>\n')
            matrix = shape.get("to_world_matrix")
            if matrix:
                values = " ".join(f"{float(value):.12g}" for value in matrix)
                f.write('    <transform name="to_world">\n')
                f.write(f'      <matrix value="{values}"/>\n')
                f.write('    </transform>\n')
            f.write('    <boolean name="face_normals" value="true"/>\n')
            f.write(f'    <ref id="mat-{itu_name}" name="bsdf"/>\n')
            f.write("  </shape>\n")
        f.write("</scene>\n")


def model_transform_matrix(shape: dict[str, Any]) -> list[float]:
    model = dict(shape.get("model", {}) or {})
    source_min = [float(v) for v in model.get("source_bbox_min", [0.0, 0.0, 0.0])]
    source_max = [float(v) for v in model.get("source_bbox_max", [1.0, 1.0, 1.0])]
    source_center = [(source_min[i] + source_max[i]) / 2.0 for i in range(3)]
    source_size = [max(source_max[i] - source_min[i], 1e-9) for i in range(3)]
    target_size = [float(v) for v in shape["size_m"]]
    scale = [target_size[i] / source_size[i] for i in range(3)]
    rotation = rotation_matrix(shape.get("rotation_deg"))
    linear = [[rotation[row][col] * scale[col] for col in range(3)] for row in range(3)]
    center = [float(v) for v in shape["center_m"]]
    translation = [center[row] - sum(linear[row][col] * source_center[col] for col in range(3)) for row in range(3)]
    return [
        linear[0][0], linear[0][1], linear[0][2], translation[0],
        linear[1][0], linear[1][1], linear[1][2], translation[1],
        linear[2][0], linear[2][1], linear[2][2], translation[2],
        0.0, 0.0, 0.0, 1.0,
    ]


def write_scene_assets(exp_root: Path, config: dict[str, Any], revision: str | None = None) -> dict[str, Any]:
    scene_dir = exp_root / "scene" if revision is None else exp_root / "scene" / "revisions" / revision
    mesh_dir = scene_dir / "meshes"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    shapes = scene_shapes(config)
    mesh_files = {}
    xml_shapes = []
    for shape in shapes:
        object_id = safe_id(str(shape["id"]))
        xml_shape = dict(shape)
        if shape.get("geometry_kind") == "model" or shape.get("model"):
            model = dict(shape.get("model", {}) or {})
            source_path = (exp_root / str(model.get("source_path", ""))).resolve()
            if exp_root.resolve() not in source_path.parents or not source_path.is_file():
                raise ValueError(f"Imported model asset is missing: {model.get('source_path')}")
            extension = source_path.suffix.lower()
            if extension not in {".obj", ".ply"}:
                raise ValueError(f"Unsupported imported model format: {extension}")
            mesh_path = mesh_dir / f"{object_id}{extension}"
            shutil.copy2(source_path, mesh_path)
            xml_shape.update({
                "mesh_type": extension[1:],
                "mesh_filename": mesh_path.name,
                "to_world_matrix": model_transform_matrix(shape),
            })
        elif shape.get("footprint_m"):
            mesh_path = mesh_dir / f"{object_id}.ply"
            write_extruded_polygon_ply(
                mesh_path,
                shape["footprint_m"],
                shape["center_m"],
                shape["size_m"],
                shape.get("rotation_deg"),
            )
        else:
            mesh_path = mesh_dir / f"{object_id}.ply"
            write_box_ply(mesh_path, shape["center_m"], shape["size_m"], shape.get("rotation_deg"))
        mesh_files[object_id] = str(mesh_path.relative_to(exp_root))
        xml_shapes.append(xml_shape)
    xml_path = scene_dir / "scene.xml"
    write_scene_xml(xml_path, xml_shapes)
    scene_assets = {
        "scene_xml": str(xml_path.relative_to(exp_root)),
        "scene_xml_path": str(xml_path),
        "mesh_files": mesh_files,
    }
    config["scene"]["scene_xml"] = scene_assets["scene_xml"]
    config["scene"]["scene_xml_path"] = scene_assets["scene_xml_path"]
    return scene_assets


def vector_sub(a: list[float], b: list[float]) -> list[float]:
    return [float(a[i]) - float(b[i]) for i in range(3)]


def boresight_angles(center_m: list[float], look_at_m: list[float]) -> dict[str, float]:
    dx, dy, dz = vector_sub(look_at_m, center_m)
    horizontal = math.hypot(dx, dy)
    return {
        "azimuth_deg": math.degrees(math.atan2(dy, dx)),
        "elevation_deg": math.degrees(math.atan2(dz, horizontal)),
    }


def building_bbox(building: dict[str, Any]) -> dict[str, list[float]]:
    vertices = box_vertices(building["center_m"], building["size_m"], building.get("rotation_deg"))
    return {
        "bbox_min": [min(point[i] for point in vertices) for i in range(3)],
        "bbox_max": [max(point[i] for point in vertices) for i in range(3)],
    }


def default_look_at(config: dict[str, Any]) -> list[float]:
    radar = config["radar"]
    center = [float(v) for v in radar["center_m"]]
    buildings = config["scene"]["buildings"]
    if not buildings:
        return [center[0] + 100.0, center[1], center[2]]
    xs = []
    ys = []
    zs = []
    for building in buildings:
        bbox = building_bbox(building)
        xs.append((bbox["bbox_min"][0] + bbox["bbox_max"][0]) / 2.0)
        ys.append((bbox["bbox_min"][1] + bbox["bbox_max"][1]) / 2.0)
        zs.append((bbox["bbox_min"][2] + bbox["bbox_max"][2]) / 2.0)
    return [sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs)]


def enrich_experiment_config(config: dict[str, Any]) -> dict[str, Any]:
    enriched = json.loads(json.dumps(config))
    scene = enriched.get("scene")
    if not isinstance(scene, dict):
        raise ValueError("Scene configuration is required")
    ground = scene.get("ground")
    if ground:
        if ground.get("material") not in MATERIAL_PRESETS:
            raise ValueError(f"Unsupported ground material: {ground.get('material')}")
        if len(ground.get("center_m", [])) != 3 or len(ground.get("size_m", [])) != 3:
            raise ValueError("Ground requires three center and size values")
        if any(float(value) <= 0 for value in ground["size_m"]):
            raise ValueError("Ground sizes must be positive")
    look_at = enriched["radar"].get("look_at_m") or default_look_at(enriched)
    enriched["radar"]["look_at_m"] = look_at
    angles = boresight_angles(enriched["radar"]["center_m"], look_at)
    if enriched["radar"].get("boresight_elevation_deg") is None:
        enriched["radar"]["boresight_elevation_deg"] = angles["elevation_deg"]
    enriched["radar"]["boresight_azimuth_deg"] = angles["azimuth_deg"]
    enriched["radar"]["boresight_geometry_note"] = "主轴指向场景建筑的几何中心；空白场景沿 X 正方向。"
    for building in enriched["scene"]["buildings"]:
        building["id"] = safe_id(str(building.get("id", "building")))
        building["name"] = str(building.get("name") or building["id"]).strip()[:120]
        if building.get("material") not in MATERIAL_PRESETS:
            raise ValueError(f"Unsupported material: {building.get('material')}")
        if len(building.get("center_m", [])) != 3 or len(building.get("size_m", [])) != 3:
            raise ValueError("Each building requires three center and size values")
        if any(float(value) <= 0 for value in building["size_m"]):
            raise ValueError("Building sizes must be positive")
        rotation = building.get("rotation_deg", [0.0, 0.0, 0.0])
        if len(rotation) != 3 or not all(math.isfinite(float(value)) for value in rotation):
            raise ValueError("Each building requires three finite rotation values")
        building["rotation_deg"] = [float(value) for value in rotation]
        building["geometry_kind"] = (
            "model"
            if building.get("model")
            else "extruded_polygon"
            if building.get("footprint_m")
            else "box"
        )
        if building["geometry_kind"] == "model":
            model = building.get("model")
            if not isinstance(model, dict) or not model.get("source_path"):
                raise ValueError("Imported model requires a source_path")
            if Path(str(model["source_path"])).suffix.lower() not in {".obj", ".ply"}:
                raise ValueError("Imported model must be OBJ or PLY")
            for key in ("source_bbox_min", "source_bbox_max"):
                if len(model.get(key, [])) != 3:
                    raise ValueError("Imported model requires source bounding box metadata")
        building.update(building_bbox(building))
    ids = [building["id"] for building in enriched["scene"]["buildings"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Building IDs must be unique")
    return enriched


def store_experiment_model(root: Path, experiment_id: str, filename: str, data: bytes) -> dict[str, Any]:
    current = load_experiment(root, experiment_id)
    extension = Path(filename).suffix.lower()
    if extension not in {".obj", ".ply"}:
        raise ValueError("Only OBJ and PLY model files are supported")
    if not data:
        raise ValueError("Model file is empty")
    asset_id = f"model_{uuid4().hex[:12]}"
    exp_root = Path(current["manifest"]["root"])
    asset_dir = exp_root / "scene" / "imports"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_path = asset_dir / f"{asset_id}{extension}"
    asset_path.write_bytes(data)
    return {
        "asset_id": asset_id,
        "original_filename": Path(filename).name,
        "format": extension[1:],
        "source_path": str(asset_path.relative_to(exp_root)),
        "preview_url": f"/api/experiments/{experiment_id}/models/{asset_path.name}",
        "size_bytes": len(data),
    }


def experiment_model_path(root: Path, experiment_id: str, asset_name: str) -> Path:
    current = load_experiment(root, experiment_id)
    exp_root = Path(current["manifest"]["root"])
    safe_name = Path(asset_name).name
    if safe_name != asset_name or Path(safe_name).suffix.lower() not in {".obj", ".ply"}:
        raise ValueError("Invalid model asset name")
    path = (exp_root / "scene" / "imports" / safe_name).resolve()
    if (exp_root / "scene" / "imports").resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(asset_name)
    return path


def create_experiment(root: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    preset_id = str((payload or {}).get("scene_preset", "two_buildings"))
    config = config_for_scene_preset(preset_id)
    if payload:
        config = deep_update(config, {key: value for key, value in payload.items() if key != "scene_preset"})
    config = enrich_experiment_config(config)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    experiment_id = f"exp_{timestamp}_{uuid4().hex[:8]}"
    exp_root = root / "experiments" / experiment_id
    input_root = exp_root / "input"
    input_root.mkdir(parents=True, exist_ok=False)
    scene_assets = write_scene_assets(exp_root, config)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "name": config.get("name", experiment_id),
        "created_at_utc": utc_now(),
        "status": "draft",
        "root": str(exp_root),
        "files": {
            "manifest": "experiment_manifest.json",
            "experiment_config": "input/experiment_config.json",
            "scene_config": "input/scene_config.json",
            "beamforming_config": "input/beamforming_config.json",
            "analysis_config": "input/analysis_config.json",
            "scene_xml": scene_assets["scene_xml"],
            "scene_meshes": "scene/meshes",
        },
    }
    write_json(exp_root / "experiment_manifest.json", manifest)
    write_json(input_root / "experiment_config.json", config)
    write_json(input_root / "scene_config.json", config["scene"])
    write_json(input_root / "beamforming_config.json", config["beamforming"])
    write_json(input_root / "analysis_config.json", config["analysis_gate"])
    return {"manifest": manifest, "config": config}


def update_experiment(root: Path, experiment_id: str, config: dict[str, Any]) -> dict[str, Any]:
    current = load_experiment(root, experiment_id)
    exp_root = Path(current["manifest"]["root"])
    updated = enrich_experiment_config(config)
    revision = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    scene_assets = write_scene_assets(exp_root, updated, revision=revision)
    manifest = current["manifest"]
    manifest["name"] = str(updated.get("name") or manifest["name"])
    manifest["updated_at_utc"] = utc_now()
    manifest["files"]["scene_xml"] = scene_assets["scene_xml"]
    input_root = exp_root / "input"
    write_json(exp_root / "experiment_manifest.json", manifest)
    write_json(input_root / "experiment_config.json", updated)
    write_json(input_root / "scene_config.json", updated["scene"])
    write_json(input_root / "beamforming_config.json", updated["beamforming"])
    write_json(input_root / "analysis_config.json", updated["analysis_gate"])
    return {"manifest": manifest, "config": updated}


def rename_experiment(root: Path, experiment_id: str, name: str) -> dict[str, Any]:
    current = load_experiment(root, experiment_id)
    current["config"]["name"] = name.strip()
    exp_root = Path(current["manifest"]["root"])
    current["manifest"]["name"] = name.strip()
    current["manifest"]["updated_at_utc"] = utc_now()
    write_json(exp_root / "experiment_manifest.json", current["manifest"])
    write_json(exp_root / "input" / "experiment_config.json", current["config"])
    return current


def list_experiments(root: Path) -> list[dict[str, Any]]:
    experiments_root = root / "experiments"
    if not experiments_root.exists():
        return []
    rows = []
    for path in sorted(experiments_root.iterdir(), reverse=True):
        manifest = path / "experiment_manifest.json"
        if manifest.exists():
            rows.append(read_json(manifest))
    return rows


def load_experiment(root: Path, experiment_id: str) -> dict[str, Any]:
    exp_root = root / "experiments" / experiment_id
    manifest_path = exp_root / "experiment_manifest.json"
    config_path = exp_root / "input" / "experiment_config.json"
    if not manifest_path.exists() or not config_path.exists():
        raise FileNotFoundError(experiment_id)
    return {
        "manifest": read_json(manifest_path),
        "config": read_json(config_path),
    }


def deep_update(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(base))
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_update(result[key], value)
        else:
            result[key] = value
    return result
