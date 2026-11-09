from functools import lru_cache
import os
from pathlib import Path
from pydantic import BaseModel

from app.bootstrap import ensure_repo_imports


class Settings(BaseModel):
    repo_root: Path
    allowed_gpu_ids: tuple[int, ...] = (0, 1, 2, 3)
    existing_campaign_root: Path
    workbench_output_root: Path
    web_cache_root: Path
    sionna_python: Path | None = None
    sionna_python_no_user_site: bool = True
    sionna_runner_timeout_s: float | None = None


def _find_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sionna_python() -> Path | None:
    env_value = os.environ.get("RADAR_SIONNA_PYTHON")
    if env_value:
        return Path(env_value)
    repo_venv = _find_repo_root() / ".venv" / "bin" / "python"
    if repo_venv.exists():
        return repo_venv
    return None


def _allowed_gpu_ids() -> tuple[int, ...]:
    value = os.environ.get("RADAR_GPU_IDS", "0,1,2,3")
    try:
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError("RADAR_GPU_IDS must be a comma-separated list of integers") from exc


@lru_cache
def get_settings() -> Settings:
    repo_root = ensure_repo_imports()
    workbench_output_root = Path(
        os.environ.get("RADAR_OUTPUT_ROOT", repo_root / "outputs" / "radar_workbench")
    ).expanduser().resolve()
    existing_campaign_root = Path(
        os.environ.get(
            "RADAR_EXAMPLE_DATA_ROOT",
            repo_root / "outputs" / "sionna_radar_campaigns" / "C002_full_radar_sensing",
        )
    ).expanduser().resolve()
    return Settings(
        repo_root=repo_root,
        allowed_gpu_ids=_allowed_gpu_ids(),
        existing_campaign_root=existing_campaign_root,
        workbench_output_root=workbench_output_root,
        web_cache_root=workbench_output_root / "web_cache",
        sionna_python=_sionna_python(),
        sionna_python_no_user_site=os.environ.get("RADAR_SIONNA_PYTHONNOUSERSITE", "1") != "0",
        sionna_runner_timeout_s=(
            float(os.environ["RADAR_SIONNA_RUNNER_TIMEOUT_S"])
            if os.environ.get("RADAR_SIONNA_RUNNER_TIMEOUT_S")
            else None
        ),
    )
