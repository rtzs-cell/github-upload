from pathlib import Path


def ensure_within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved == resolved_root or resolved_root in resolved.parents:
        return resolved
    raise ValueError(f"Path {resolved} is outside allowed root {resolved_root}")


def relpath(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)
