from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_imports() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    experiments_src = repo_root / "experiments" / "sionna_radar" / "src"
    if str(experiments_src) not in sys.path:
        sys.path.insert(0, str(experiments_src))
    return repo_root
