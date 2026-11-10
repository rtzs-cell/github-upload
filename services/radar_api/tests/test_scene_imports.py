from pathlib import Path
import json

from fastapi.testclient import TestClient

from app.api import experiments as experiments_api
from app.config import Settings
from app.main import app
from app.core.scene_imports import build_overpass_query, parse_scene_import
from app.core.two_building_scene import write_extruded_polygon_ply


REPO_ROOT = Path(__file__).resolve().parents[3]


def _osm_payload() -> bytes:
    return b"""<osm>
  <node id='1' lat='31.0000' lon='121.0000'/>
  <node id='2' lat='31.0000' lon='121.0002'/>
  <node id='3' lat='31.0002' lon='121.0002'/>
  <node id='4' lat='31.0002' lon='121.0000'/>
  <way id='42'>
    <nd ref='1'/><nd ref='2'/><nd ref='3'/><nd ref='4'/><nd ref='1'/>
    <tag k='building' v='office'/>
    <tag k='building:levels' v='5'/>
  </way>
</osm>"""


def test_overpass_query_contains_building_bbox() -> None:
    query = build_overpass_query(31.0, 121.0, 31.1, 121.1)
    assert '[out:json]' in query
    assert 'way["building"]' in query
    assert 'way["building:part"]' in query
    assert '(31.0000000,121.0000000,31.1000000,121.1000000)' in query
    assert 'out geom' in query


def test_osm_import_projects_footprint_and_height() -> None:
    result = parse_scene_import("map.osm", _osm_payload())
    assert result["source_type"] == "osm"
    assert result["object_count"] == 1
    building = result["buildings"][0]
    assert building["source"]["id"] == "42"
    assert building["size_m"][2] == 16.0
    assert 18.0 < building["size_m"][0] < 20.0
    assert 21.0 < building["size_m"][1] < 23.0
    assert len(building["footprint_m"]) == 4
    assert building["geometry_kind"] == "extruded_polygon"


def test_extruded_polygon_ply_preserves_concave_footprint(tmp_path: Path) -> None:
    footprint = [(-2.0, -2.0), (2.0, -2.0), (2.0, -1.0), (0.0, -1.0), (0.0, 2.0), (-2.0, 2.0)]
    mesh_path = tmp_path / "concave.ply"
    write_extruded_polygon_ply(mesh_path, footprint, [10.0, 20.0, 3.0], [4.0, 4.0, 6.0])
    lines = mesh_path.read_text(encoding="ascii").splitlines()
    vertex_count = int(next(line.split()[-1] for line in lines if line.startswith("element vertex")))
    face_count = int(next(line.split()[-1] for line in lines if line.startswith("element face")))
    header_end = lines.index("end_header")
    vertices = [tuple(map(float, line.split())) for line in lines[header_end + 1:header_end + 1 + vertex_count]]
    faces = [line.split() for line in lines[header_end + 1 + vertex_count:header_end + 1 + vertex_count + face_count]]
    assert vertex_count == 12
    assert face_count == 20
    assert all(face[0] == "3" and all(0 <= int(index) < vertex_count for index in face[1:]) for face in faces)
    assert len({(round(vertex[0], 6), round(vertex[1], 6)) for vertex in vertices[:6]}) == 6
    assert {round(vertex[2], 6) for vertex in vertices} == {0.0, 6.0}


def test_geojson_import_reads_building_properties() -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": "b-7",
            "properties": {"building": "yes", "height": "9 m", "name": "Geo Tower"},
            "geometry": {"type": "Polygon", "coordinates": [[
                [121.0, 31.0], [121.0001, 31.0], [121.0001, 31.0001], [121.0, 31.0001], [121.0, 31.0]
            ]]},
        }],
    }
    result = parse_scene_import("buildings.geojson", json.dumps(payload).encode())
    assert result["source_type"] == "geojson"
    assert result["buildings"][0]["name"] == "Geo Tower"
    assert result["buildings"][0]["size_m"][2] == 9.0


def test_osm_import_endpoint_supports_hybrid_scene(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        repo_root=REPO_ROOT,
        existing_campaign_root=REPO_ROOT / "outputs" / "sionna_radar_campaigns" / "C002_full_radar_sensing",
        workbench_output_root=tmp_path / "workbench",
        web_cache_root=tmp_path / "cache",
    )
    monkeypatch.setattr(experiments_api, "get_settings", lambda: settings)
    client = TestClient(app)

    created = client.post("/api/experiments", json={"config": {"scene_preset": "empty", "name": "osm hybrid"}})
    assert created.status_code == 200, created.text
    experiment = created.json()
    experiment_id = experiment["manifest"]["experiment_id"]

    imported = client.post(
        f"/api/experiments/{experiment_id}/scene-imports?filename=map.osm",
        content=_osm_payload(),
        headers={"content-type": "application/octet-stream"},
    )
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["object_count"] == 1
    assert result["source_path"].startswith("scene/imports/")
    assert (Path(experiment["manifest"]["root"]) / result["source_path"]).exists()

    config = experiment["config"]
    config["scene"]["kind"] = "hybrid"
    config["scene"]["buildings"] = result["buildings"]
    saved = client.put(f"/api/experiments/{experiment_id}", json={"config": config})
    assert saved.status_code == 200, saved.text
    saved_config = saved.json()["config"]
    assert saved_config["scene"]["buildings"][0]["source"]["type"] == "osm"
    assert saved_config["scene"]["buildings"][0]["geometry_kind"] == "extruded_polygon"
    assert Path(saved_config["scene"]["scene_xml_path"]).exists()
