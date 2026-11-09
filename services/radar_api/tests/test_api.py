from pathlib import Path

from fastapi.testclient import TestClient

from app.deps import get_job_store
from app.main import app
from app.workers.gpu_scheduler import GPUScheduler
from app.api.simulations import make_job_id


RUN_ID = "MM_C002full_Pp0_p0_BposY_S501_N500k"


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["allowed_gpu_ids"] == [0, 1, 2, 3]
    assert body["sionna_runtime"]["mode"] in {"external_python", "in_process"}


def test_campaign_runs_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/campaigns/c002_full_existing/runs")
    assert response.status_code == 200
    body = response.json()
    assert len(body["runs"]) == 30
    assert body["runs"][0]["run_id"]


def test_result_paths_endpoint_builds_cache() -> None:
    client = TestClient(app)
    response = client.get(f"/api/results/{RUN_ID}/paths?top_k=5")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == RUN_ID
    assert 1 <= len(body["paths"]) <= 5
    path = body["paths"][0]
    assert len(path["polyline_m"]) >= 2
    assert {"aod_azimuth_deg", "aod_elevation_deg", "aoa_azimuth_deg", "aoa_elevation_deg"}.issubset(path)
    assert isinstance(path["interactions"], list)


def test_path_export_endpoint_saves_archive() -> None:
    client = TestClient(app)
    response = client.post(
        f"/api/results/{RUN_ID}/path_exports",
        json={
            "draft_config": {
                "center_m": [0.0, 0.0, 10.0],
                "look_at_m": [30.0, 0.0, 10.0],
                "az_width_deg": 120.0,
                "el_min_deg": 0.0,
                "el_max_deg": 40.0,
            },
            "top_k": 3,
            "kind": "all",
            "in_fov": True,
            "note": "pytest export",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == RUN_ID
    assert 1 <= body["path_count"] <= 3
    for name in ["manifest", "paths", "path_summary", "radar_config", "run_metadata"]:
        assert Path(body["files"][name]).exists()


def test_unknown_run_returns_404() -> None:
    client = TestClient(app)
    response = client.get("/api/results/not_a_run/metadata")
    assert response.status_code == 404


def test_simulation_request_rejects_invalid_gpu() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/simulations",
        json={
            "scene_id": "simple_street_canyon",
            "mode": "single_pose",
            "gpu_ids": [9],
            "radar": {
                "center_m": [0.0, 0.0, 10.0],
                "look_at_m": [0.0, 30.0, 10.0],
                "tx_rx_baseline_m": 0.1,
            },
            "propagation": {
                "frequency_hz": 28000000000.0,
                "bandwidth_hz": 1000000000.0,
            },
            "scattering": {
                "enabled": True,
                "coefficient": 0.5,
                "pattern": "backscattering",
                "alpha_r": 20,
                "alpha_i": 20,
                "lambda_": 0.3,
            },
            "tx_array": {"num_rows": 1, "num_cols": 1},
            "rx_array": {"num_rows": 16, "num_cols": 16},
            "path_solver": {"max_depth": 2, "samples_per_src": 10000},
            "observation": {},
            "compute": {"samples_per_src": 10000, "seed": 501},
        },
    )
    assert response.status_code == 400


def valid_simulation_payload() -> dict:
    return {
        "scene_id": "simple_street_canyon",
        "mode": "single_pose",
        "gpu_ids": [0, 1, 2, 3],
        "radar": {
            "center_m": [0.0, 0.0, 10.0],
            "look_at_m": [0.0, 30.0, 10.0],
            "tx_rx_baseline_m": 0.1,
            "az_width_deg": 120.0,
            "el_min_deg": 0.0,
            "el_max_deg": 40.0,
            "rmax_m": 200.0,
            "range_bin_m": 0.15,
            "angle_bin_deg": 2.0,
        },
        "propagation": {
            "frequency_hz": 28000000000.0,
            "bandwidth_hz": 1000000000.0,
        },
        "scattering": {
            "enabled": True,
            "coefficient": 0.5,
            "pattern": "backscattering",
            "alpha_r": 20,
            "alpha_i": 20,
            "lambda_": 0.3,
        },
        "tx_array": {"num_rows": 1, "num_cols": 1},
        "rx_array": {"num_rows": 16, "num_cols": 16},
        "path_solver": {"max_depth": 2, "samples_per_src": 10000},
        "observation": {},
        "compute": {"samples_per_src": 10000, "seed": 501},
    }


def test_simulation_request_returns_queued(monkeypatch) -> None:
    def fake_submit_single(self: GPUScheduler, job_id: str, request: dict) -> None:
        gpu_ids = request.get("gpu_ids", [0])
        self.validate_gpu_ids(gpu_ids)
        self.job_store.create(job_id, request, gpu_ids)

    monkeypatch.setattr(GPUScheduler, "submit_single", fake_submit_single)
    client = TestClient(app)
    response = client.post("/api/simulations", json=valid_simulation_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    status = client.get(body["status_url"])
    assert status.status_code == 200
    assert status.json()["status"] == "queued"


def test_make_job_id_is_unique_for_retries() -> None:
    payload = {"scene_id": "simple_street_canyon", "radar": {"seed": 501}}
    first = make_job_id(payload)
    second = make_job_id(payload)
    assert first != second
    assert first.startswith("job_")
    assert second.startswith("job_")


def test_simulation_request_rejects_wrong_tx_weight_count() -> None:
    payload = valid_simulation_payload()
    payload["tx_array"] = {"num_rows": 1, "num_cols": 2, "pattern": "radar_array"}
    payload["observation"] = {
        "beamforming": {
            "tx_weight_mode": "custom_complex_weights",
            "tx_custom_weights_json": "[[1, 0]]",
        }
    }

    response = TestClient(app).post("/api/simulations", json=payload)

    assert response.status_code == 422
    assert "complex weight count" in response.text
