from pathlib import Path
import sys
import zipfile

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.workers.simulation_worker import run_experiment_external
from app.api import results as results_api
from app.api import experiments as experiments_api


RUN_ID = "MM_C002full_Pp0_p0_BposY_S501_N500k"
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_two_building_template_and_experiment_create(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        repo_root=REPO_ROOT,
        existing_campaign_root=REPO_ROOT / "outputs" / "sionna_radar_campaigns" / "C002_full_radar_sensing",
        workbench_output_root=tmp_path / "workbench",
        web_cache_root=tmp_path / "cache",
    )
    monkeypatch.setattr(experiments_api, "get_settings", lambda: settings)
    client = TestClient(app)
    template = client.get("/api/experiments/templates/two_buildings")
    assert template.status_code == 200
    body = template.json()
    assert body["scene"]["kind"] == "parametric_two_buildings"
    assert body["scene"]["buildings"][0]["id"] == "building_A"
    assert body["arrays"]["tx"]["pattern"] == "radar_array"
    assert body["arrays"]["tx"]["num_rows"] == 8
    assert body["solver"]["initial_ray_sampling"]["mode"] == "full_sphere"
    assert body["waveform"]["num_chirps"] == 32
    assert body["receiver"]["noise_figure_db"] == 8.0

    response = client.post(
        "/api/experiments",
        json={
            "config": {
                "name": "pytest two building experiment",
                "scene": {
                    "buildings": [
                        {
                            "id": "building_A",
                            "center_m": [430.0, -35.0, 30.0],
                            "size_m": [45.0, 30.0, 60.0],
                            "material": "concrete",
                        },
                        {
                            "id": "building_B",
                            "center_m": [480.0, 45.0, 60.0],
                            "size_m": [55.0, 35.0, 120.0],
                            "material": "concrete",
                        },
                    ]
                },
            }
        },
    )
    assert response.status_code == 200
    created = response.json()
    assert created["manifest"]["experiment_id"].startswith("exp_")
    assert created["config"]["radar"]["look_at_m"]
    assert created["config"]["scene"]["buildings"][1]["bbox_max"][2] == 120.0
    exp_root = Path(created["manifest"]["root"])
    assert (exp_root / created["manifest"]["files"]["scene_xml"]).exists()
    assert (exp_root / "scene" / "meshes" / "building_A.ply").exists()
    assert (exp_root / "scene" / "meshes" / "building_B.ply").exists()
    assert created["config"]["scene"]["scene_xml_path"].endswith("scene.xml")

    loaded = client.get(f"/api/experiments/{created['manifest']['experiment_id']}")
    assert loaded.status_code == 200
    assert loaded.json()["manifest"]["name"] == "pytest two building experiment"


def test_scene_presets_revision_and_experiment_rename(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        repo_root=REPO_ROOT,
        existing_campaign_root=REPO_ROOT / "outputs" / "sionna_radar_campaigns" / "C002_full_radar_sensing",
        workbench_output_root=tmp_path / "workbench",
        web_cache_root=tmp_path / "cache",
    )
    monkeypatch.setattr(experiments_api, "get_settings", lambda: settings)
    client = TestClient(app)
    presets = client.get("/api/experiments/presets")
    assert presets.status_code == 200
    assert {item["id"] for item in presets.json()["scenes"]} == {"empty", "two_buildings", "street_canyon"}
    assert "metal" in presets.json()["materials"]

    created_response = client.post("/api/experiments", json={"config": {"scene_preset": "empty", "name": "pytest editable scene"}})
    assert created_response.status_code == 200
    created = created_response.json()
    experiment_id = created["manifest"]["experiment_id"]
    old_scene_path = Path(created["config"]["scene"]["scene_xml_path"])
    old_scene_text = old_scene_path.read_text(encoding="utf-8")
    assert created["config"]["scene"]["buildings"] == []

    updated_config = created["config"]
    updated_config["scene"]["buildings"] = [{
        "id": "office_block",
        "center_m": [120.0, 10.0, 20.0],
        "size_m": [40.0, 30.0, 40.0],
        "material": "glass",
    }]
    updated = client.put(f"/api/experiments/{experiment_id}", json={"config": updated_config})
    assert updated.status_code == 200
    revised_scene_path = Path(updated.json()["config"]["scene"]["scene_xml_path"])
    assert revised_scene_path != old_scene_path
    assert "/revisions/" in revised_scene_path.as_posix()
    assert old_scene_path.read_text(encoding="utf-8") == old_scene_text
    assert revised_scene_path.exists()
    assert "office_block.ply" in revised_scene_path.with_name("meshes").joinpath("office_block.ply").as_posix()

    renamed = client.patch(f"/api/experiments/{experiment_id}/name", json={"name": "城区玻璃建筑测试"})
    assert renamed.status_code == 200
    assert renamed.json()["manifest"]["name"] == "城区玻璃建筑测试"
    assert client.get(f"/api/experiments/{experiment_id}").json()["config"]["name"] == "城区玻璃建筑测试"

    invalid = updated.json()["config"]
    invalid["scene"]["ground"]["material"] = "unknown"
    response = client.put(f"/api/experiments/{experiment_id}", json={"config": invalid})
    assert response.status_code == 400


def test_rotated_box_and_imported_model_are_written_to_scene(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        repo_root=REPO_ROOT,
        existing_campaign_root=REPO_ROOT / "outputs" / "sionna_radar_campaigns" / "C002_full_radar_sensing",
        workbench_output_root=tmp_path / "workbench",
        web_cache_root=tmp_path / "cache",
    )
    monkeypatch.setattr(experiments_api, "get_settings", lambda: settings)
    client = TestClient(app)
    created = client.post("/api/experiments", json={"config": {"scene_preset": "empty", "name": "model import"}}).json()
    experiment_id = created["manifest"]["experiment_id"]

    obj = b"v -1 -2 0\nv 1 -2 0\nv 1 2 3\nv -1 2 3\nf 1 2 3\nf 1 3 4\n"
    uploaded = client.post(
        f"/api/experiments/{experiment_id}/models?filename=tower.obj",
        content=obj,
        headers={"content-type": "application/octet-stream"},
    )
    assert uploaded.status_code == 200
    asset = uploaded.json()
    assert asset["format"] == "obj"
    assert client.get(asset["preview_url"]).content == obj

    config = created["config"]
    config["scene"]["buildings"] = [
        {
            "id": "rotated_box",
            "center_m": [20.0, 0.0, 5.0],
            "size_m": [10.0, 4.0, 10.0],
            "rotation_deg": [0.0, 0.0, 90.0],
            "material": "brick",
        },
        {
            "id": "tower_model",
            "center_m": [40.0, 10.0, 15.0],
            "size_m": [20.0, 10.0, 30.0],
            "rotation_deg": [0.0, 0.0, 30.0],
            "material": "metal",
            "geometry_kind": "model",
            "model": {
                **asset,
                "source_bbox_min": [-1.0, -2.0, 0.0],
                "source_bbox_max": [1.0, 2.0, 3.0],
            },
        },
    ]
    response = client.put(f"/api/experiments/{experiment_id}", json={"config": config})
    assert response.status_code == 200, response.text
    updated = response.json()["config"]
    rotated = updated["scene"]["buildings"][0]
    assert round(rotated["bbox_max"][0] - rotated["bbox_min"][0], 6) == 4.0
    assert round(rotated["bbox_max"][1] - rotated["bbox_min"][1], 6) == 10.0
    scene_path = Path(updated["scene"]["scene_xml_path"])
    scene_text = scene_path.read_text(encoding="utf-8")
    assert '<shape type="obj" id="mesh-tower_model">' in scene_text
    assert '<matrix value="' in scene_text
    assert (scene_path.parent / "meshes" / "tower_model.obj").read_bytes() == obj


def test_readonly_result_cannot_be_renamed() -> None:
    client = TestClient(app)
    response = client.patch(f"/api/results/{RUN_ID}/name", json={"name": "不可写名称"})
    assert response.status_code == 403


def test_local_result_name_is_written_without_renaming_run_directory(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        repo_root=REPO_ROOT,
        existing_campaign_root=REPO_ROOT / "outputs" / "sionna_radar_campaigns" / "C002_full_radar_sensing",
        workbench_output_root=tmp_path / "workbench",
        web_cache_root=tmp_path / "cache",
    )
    run_id = "local_result_001"
    run_dir = settings.workbench_output_root / "campaigns" / "campaign_001" / "runs" / run_id
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(results_api, "get_settings", lambda: settings)
    response = TestClient(app).patch(f"/api/results/{run_id}/name", json={"name": "主路口夜间测量"})
    assert response.status_code == 200
    assert run_dir.exists()
    assert not (run_dir.parent / "主路口夜间测量").exists()
    assert "主路口夜间测量" in (run_dir / "display_name.json").read_text(encoding="utf-8")


def test_path_statistics_and_result_bundle() -> None:
    client = TestClient(app)
    response = client.get(f"/api/results/{RUN_ID}/path_statistics")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["run_id"] == RUN_ID
    assert body["summary"]["valid_path_count"] > 0
    assert body["summary"]["analysis_gate_path_count"] >= 0
    for path in body["files"].values():
        assert Path(path).exists()

    bundle_response = client.get(f"/api/results/{RUN_ID}/result_bundle")
    assert bundle_response.status_code == 200
    bundle_path = Path(bundle_response.json()["bundle_path"])
    assert bundle_path.exists()
    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "analysis/path_statistics.json" in names
    assert "analysis/paths.csv" in names
    assert "analysis/building_path_statistics.csv" in names
    assert "analysis/analysis_gate_mpc.csv" in names
    assert "analysis/analysis_gate_mpc_summary.json" in names
    assert "figures/analysis_gate_mpc.png" in names


def test_mpc_analysis_endpoint() -> None:
    client = TestClient(app)
    response = client.get(f"/api/results/{RUN_ID}/mpc_analysis")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["run_id"] == RUN_ID
    assert body["summary"]["valid_path_count"] > 0
    assert body["summary"]["analysis_gate_path_count"] >= 0
    assert body["summary"]["mpc_panorama"]["schema_version"] == "1.2.0"
    assert body["summary"]["mpc_panorama"]["panorama_shape"] == [540, 1080]
    assert body["summary"]["mpc_panorama"]["coefficient_selection"] == "rx=0, rx_ant=0, tx=0, tx_ant=0"
    for name in ["mpc_panorama_array", "mpc_panorama", "mpc_view_front", "mpc_view_right", "mpc_view_back", "mpc_view_left"]:
        assert name in body["files"]
    for path in body["files"].values():
        assert Path(path).exists()


def test_beamforming_analysis_endpoint() -> None:
    client = TestClient(app)
    response = client.get(f"/api/results/{RUN_ID}/beamforming")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["rx_mode"] == "uniform"
    assert body["summary"]["rx_weight_count"] == 256
    assert body["summary"]["cir_axes"]["rx_axis"] == 1
    assert body["summary"]["top_paths"]
    assert "rx_steering_pattern_figure" in body["files"]
    assert "tx_radiation_pattern_figure" in body["files"]
    for path in body["files"].values():
        assert Path(path).exists()


def test_beamforming_endpoint_does_not_mutate_run_snapshot() -> None:
    client = TestClient(app)
    response = client.get(f"/api/results/{RUN_ID}/beamforming?rx_mode=steering_vector")
    assert response.status_code == 409


def test_fmcw_analysis_endpoint() -> None:
    client = TestClient(app)
    response = client.get(f"/api/results/{RUN_ID}/fmcw")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["model"].startswith("hybrid complex FMCW")
    assert body["summary"]["range_resolution_m"] > 0
    assert body["summary"]["synthesized_path_count"] > 0
    assert Path(body["files"]["range_doppler"]).exists()
    assert Path(body["files"]["range_doppler_figure"]).exists()


def test_split_download_catalog_and_lightweight_bundle() -> None:
    client = TestClient(app)
    response = client.get(f"/api/results/{RUN_ID}/downloads")
    assert response.status_code == 200
    artifacts = {item["artifact_id"]: item for item in response.json()["artifacts"]}
    assert artifacts["cir"]["size_bytes"] > 0
    assert artifacts["paths_raw"]["size_bytes"] > 0
    assert artifacts["analysis_bundle"]["generated"] is True
    assert artifacts["mpc_panorama_array"]["size_bytes"] > 0
    assert artifacts["mpc_view_front"]["size_bytes"] > 0

    bundle_response = client.get(f"/api/results/{RUN_ID}/downloads/analysis_bundle")
    assert bundle_response.status_code == 200
    bundle_path = Path(bundle_response.headers["content-disposition"].split('filename="', 1)[1].rstrip('"'))
    written_path = REPO_ROOT / "outputs" / "radar_workbench" / "result_bundles" / bundle_path.name
    assert written_path.exists()
    with zipfile.ZipFile(written_path) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "raw/cir.npz" not in names
    assert "analysis/paths.csv" not in names
    assert any(name.startswith("figures/") for name in names)

    direct_response = client.get(f"/api/results/{RUN_ID}/downloads/metrics")
    assert direct_response.status_code == 200
    assert direct_response.headers["content-disposition"].endswith('filename="metrics.json"')


def test_external_runner_bridge_metadata_only(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    settings = Settings(
        repo_root=repo_root,
        existing_campaign_root=repo_root / "outputs" / "sionna_radar_campaigns" / "C002_full_radar_sensing",
        workbench_output_root=tmp_path / "workbench",
        web_cache_root=tmp_path / "web_cache",
        sionna_python=Path(sys.executable),
        sionna_python_no_user_site=True,
        sionna_runner_timeout_s=30.0,
    )
    config = {
        "run_id": "pytest_external_metadata_only",
        "mode": "metadata_only",
        "scene": "none",
        "milestone": "TEST",
        "purpose": "external runner bridge test",
        "archive": {"output_root": str(tmp_path / "campaign")},
    }
    metrics = run_experiment_external(config, settings, gpu_id=None)
    assert metrics["run_id"] == "pytest_external_metadata_only"
    assert metrics["status"] == "complete"
    assert (tmp_path / "campaign" / "runs" / "pytest_external_metadata_only" / "metrics.json").exists()
