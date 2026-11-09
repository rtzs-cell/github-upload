from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from app.config import Settings


def runtime_summary(settings: Settings) -> dict[str, Any]:
    python = settings.sionna_python
    return {
        "mode": "external_python" if python is not None else "in_process",
        "python": str(python) if python is not None else None,
        "python_exists": bool(python and python.exists()),
        "python_no_user_site": settings.sionna_python_no_user_site,
        "probe_endpoint": "/api/health/sionna_runtime",
    }


def probe_sionna_runtime(settings: Settings, timeout_s: float = 30.0) -> dict[str, Any]:
    python = settings.sionna_python
    if python is None or not python.exists():
        return {
            **runtime_summary(settings),
            "available": False,
            "error": "RADAR_SIONNA_PYTHON is not configured or does not exist",
        }
    env = os.environ.copy()
    env["PYTHONPATH"] = str(settings.repo_root / "experiments" / "sionna_radar" / "src")
    env["CUDA_VISIBLE_DEVICES"] = "-1"
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    if settings.sionna_python_no_user_site:
        env["PYTHONNOUSERSITE"] = "1"
    code = (
        "import importlib.metadata as metadata\n"
        "import inspect\n"
        "import json\n"
        "import sionna.rt as rt\n"
        "from sionna_radar.runner import scene_path\n"
        "print('sionna_rt_import_ok')\n"
        "print('runtime_versions=' + json.dumps({\n"
        "    'sionna_rt': metadata.version('sionna-rt'),\n"
        "    'mitsuba': metadata.version('mitsuba'),\n"
        "    'drjit': metadata.version('drjit'),\n"
        "    'module_path': inspect.getfile(rt),\n"
        "    'path_solver_available': hasattr(rt, 'PathSolver'),\n"
        "}, sort_keys=True))\n"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code],
            cwd=str(settings.repo_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **runtime_summary(settings),
            "available": False,
            "error": f"Sionna RT import probe timed out after {timeout_s:.1f} s",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    versions = None
    for line in result.stdout.splitlines():
        if line.startswith("runtime_versions="):
            try:
                versions = json.loads(line.removeprefix("runtime_versions="))
            except json.JSONDecodeError:
                versions = None
            break
    return {
        **runtime_summary(settings),
        "available": result.returncode == 0,
        "returncode": result.returncode,
        "versions": versions,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }
