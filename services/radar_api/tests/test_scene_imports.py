from pathlib import Path
import json

from fastapi.testclient import TestClient

from app.api import experiments as experiments_api
from app.config import Settings
from app.main import app
from app.core.scene_imports import parse_scene_import


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
    assert Path(saved_config["scene"]["scene_xml_path"]).exists()
