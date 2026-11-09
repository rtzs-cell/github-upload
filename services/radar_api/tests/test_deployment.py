import importlib.util
import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core.campaign_registry import CampaignRegistry
from app.main import app


def test_embedded_frontend_root_returns_html() -> None:
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<div id=\"root\"></div>" in response.text


def test_registry_works_without_optional_example_data(tmp_path: Path) -> None:
    output_root = tmp_path / "workbench"
    campaign_root = output_root / "campaigns" / "local_measurement"
    reports_root = campaign_root / "reports"
    reports_root.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "run_id": "measurement_001",
                "pose_id": "pose_001",
                "boresight_id": "forward",
                "x_m": 0.0,
                "y_m": 0.0,
                "z_m": 10.0,
                "look_x_m": 30.0,
                "look_y_m": 0.0,
                "look_z_m": 10.0,
                "boresight_az_deg": 0.0,
                "boresight_el_deg": 0.0,
                "valid_path_count": 1,
                "dominant_range_m": 15.0,
                "range_max_m": 15.0,
                "fov_energy_fraction": 1.0,
                "fov_path_fraction": 1.0,
                "energy_in_fov": 1.0,
                "max_interaction_depth": 1,
                "samples_per_src": 1000,
                "seed": 1,
            }
        ]
    ).to_csv(reports_root / "runs_index.csv", index=False)

    settings = Settings(
        repo_root=tmp_path,
        existing_campaign_root=tmp_path / "missing-example",
        workbench_output_root=output_root,
        web_cache_root=output_root / "web_cache",
    )
    registry = CampaignRegistry(settings)

    campaigns = registry.list_campaigns()
    assert [item.campaign_id for item in campaigns] == ["workbench_local", "local_measurement"]
    assert [item.run_id for item in registry.load_runs("workbench_local")] == ["measurement_001"]


def test_settings_use_portable_environment_paths(monkeypatch, tmp_path: Path) -> None:
    output_root = tmp_path / "results"
    example_root = tmp_path / "examples"
    sionna_python = tmp_path / "runtime" / "python"
    monkeypatch.setenv("RADAR_OUTPUT_ROOT", str(output_root))
    monkeypatch.setenv("RADAR_EXAMPLE_DATA_ROOT", str(example_root))
    monkeypatch.setenv("RADAR_SIONNA_PYTHON", str(sionna_python))
    monkeypatch.setenv("RADAR_GPU_IDS", "2, 5")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.workbench_output_root == output_root
        assert settings.existing_campaign_root == example_root
        assert settings.sionna_python == sionna_python
        assert settings.allowed_gpu_ids == (2, 5)
    finally:
        get_settings.cache_clear()


def test_rebase_updates_only_editable_experiment_paths(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "rebase_radar_paths.py"
    spec = importlib.util.spec_from_file_location("rebase_radar_paths", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    experiment_root = tmp_path / "outputs" / "radar_workbench" / "experiments" / "experiment_001"
    input_root = experiment_root / "input"
    scene_root = experiment_root / "scene" / "revisions" / "revision_001"
    input_root.mkdir(parents=True)
    scene_root.mkdir(parents=True)
    relative_scene = "scene/revisions/revision_001/scene.xml"
    (experiment_root / "experiment_manifest.json").write_text(
        json.dumps({"root": "/old/location", "files": {"scene_xml": relative_scene}}),
        encoding="utf-8",
    )
    (input_root / "experiment_config.json").write_text(
        json.dumps({"scene": {"scene_xml": relative_scene, "scene_xml_path": "/old/scene.xml"}}),
        encoding="utf-8",
    )
    (input_root / "scene_config.json").write_text(
        json.dumps({"scene_xml": relative_scene, "scene_xml_path": "/old/scene.xml"}),
        encoding="utf-8",
    )
    immutable_result = tmp_path / "outputs" / "radar_workbench" / "campaigns" / "result" / "config.json"
    immutable_result.parent.mkdir(parents=True)
    immutable_result.write_text('{"scene_xml_path": "/old/result.xml"}', encoding="utf-8")

    assert module.rebase_experiment(experiment_root) == 1
    config = json.loads((input_root / "experiment_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((experiment_root / "experiment_manifest.json").read_text(encoding="utf-8"))
    assert manifest["root"] == str(experiment_root.resolve())
    assert config["scene"]["scene_xml_path"] == str((experiment_root / relative_scene).resolve())
    assert json.loads(immutable_result.read_text(encoding="utf-8"))["scene_xml_path"] == "/old/result.xml"
