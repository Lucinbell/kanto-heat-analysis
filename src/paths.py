"""
Repository path resolution.

Reads .local_env at the repo root to pick up machine-specific overrides.
Notebooks and scripts should import RAW_DIR from here rather than
hard-coding paths.

Usage
-----
    from src.paths import RAW_DIR, REPO_ROOT
    ds = xr.open_dataset(RAW_DIR / "era5land_2m_temperature_2023_07_12.nc")
"""

import pathlib

REPO_ROOT = pathlib.Path(__file__).parents[1]

def _read_local_env() -> dict[str, str]:
    """Parse .local_env (KEY=VALUE, comments and blanks ignored)."""
    env_file = REPO_ROOT / ".local_env"
    if not env_file.exists():
        return {}
    result = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


_local = _read_local_env()

RAW_DIR: pathlib.Path = pathlib.Path(
    _local.get("DATA_RAW_DIR", REPO_ROOT / "data" / "raw")
)
PROCESSED_DIR: pathlib.Path = REPO_ROOT / "data" / "processed"
FIGURES_DIR: pathlib.Path = REPO_ROOT / "figures"
