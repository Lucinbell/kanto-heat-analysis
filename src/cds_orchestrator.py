"""
Stateful, idempotent CDS API download orchestrator.

Tracks completed downloads in data/download_manifest.json so the script is
safe to re-run — already-complete entries are skipped without a new API call.

ERA5-Land always delivers a zip archive (containing data_0.nc) on the new CDS
infrastructure, even when data_format="netcdf" is specified.  ERA5 proper
delivers a plain NetCDF4 file.  _extract_if_zipped() handles both cases.

Usage
-----
    from src.cds_orchestrator import download_era5land

    path = download_era5land(
        variable="2m_temperature",
        year="2023",
        months=["06", "07", "08"],
        area=[37, 138, 35, 141],          # [N, W, S, E]
        dest_name="era5land_2m_temperature_2023.nc",
    )
"""

import json
import os
import pathlib
import zipfile

import cdsapi

REPO_ROOT = pathlib.Path(__file__).parents[1]
DATA_RAW = REPO_ROOT / "data" / "raw"
MANIFEST_PATH = REPO_ROOT / "data" / "download_manifest.json"
SECRETS = REPO_ROOT / ".secrets" / "dylan_wang.cdsapirc"

_DAYS_ALL = [f"{d:02d}" for d in range(1, 32)]
_HOURS_ALL = [f"{h:02d}:00" for h in range(24)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def download_era5land(variable, year, months, area, dest_name):
    """Download one ERA5-Land variable for one year (or subset of months).

    Parameters
    ----------
    variable : str
        CDS variable name, e.g. ``"2m_temperature"`` or ``"total_precipitation"``.
    year : str or int
        Four-digit year.
    months : list of str
        Zero-padded month strings, e.g. ``["06", "07", "08"]``.
    area : list of float
        Bounding box as ``[N, W, S, E]``.
    dest_name : str
        Target filename inside ``data/raw/``, e.g.
        ``"era5land_2m_temperature_2023.nc"``.

    Returns
    -------
    pathlib.Path
        Path to the final ``.nc`` file.
    """
    manifest = _load_manifest()

    if manifest.get(dest_name, {}).get("status") == "complete":
        dest_path = DATA_RAW / dest_name
        print(f"[orchestrator] Already complete — skipping: {dest_name}")
        return dest_path

    DATA_RAW.mkdir(parents=True, exist_ok=True)
    tmp_path = DATA_RAW / f"_tmp_{dest_name}"

    client = _make_client()
    client.retrieve(
        "reanalysis-era5-land",
        {
            "variable": [variable],
            "year": str(year),
            "month": months,
            "day": _DAYS_ALL,
            "time": _HOURS_ALL,
            "area": area,
            "data_format": "netcdf",
        },
        str(tmp_path),
    )

    dest_path = DATA_RAW / dest_name
    _extract_if_zipped(tmp_path, dest_path)

    manifest[dest_name] = {"status": "complete", "path": str(dest_path)}
    _save_manifest(manifest)

    print(f"[orchestrator] Saved: {dest_path}")
    return dest_path


def download_era5(variable, year, months, pressure_level, area, dest_name, times=None):
    """Download one ERA5 pressure-level variable for one year (or subset of months).

    Parameters
    ----------
    variable : str
        CDS variable name, e.g. ``"geopotential"`` or ``"u_component_of_wind"``.
    year : str or int
        Four-digit year.
    months : list of str
        Zero-padded month strings, e.g. ``["07"]``.
    pressure_level : str or int
        Pressure level in hPa, e.g. ``"500"`` or ``"850"``.
    area : list of float
        Bounding box as ``[N, W, S, E]``.
    dest_name : str
        Target filename inside ``data/raw/``, e.g.
        ``"era5_geopotential_500hPa_2023_07.nc"``.
    times : list of str, optional
        Hour strings, e.g. ``["00:00"]`` for daily snapshots. Defaults to all
        24 hours (consistent with download_era5land behaviour).

    Returns
    -------
    pathlib.Path
        Path to the final ``.nc`` file.
    """
    manifest = _load_manifest()

    if manifest.get(dest_name, {}).get("status") == "complete":
        dest_path = DATA_RAW / dest_name
        print(f"[orchestrator] Already complete — skipping: {dest_name}")
        return dest_path

    DATA_RAW.mkdir(parents=True, exist_ok=True)
    tmp_path = DATA_RAW / f"_tmp_{dest_name}"

    client = _make_client()
    client.retrieve(
        "reanalysis-era5-pressure-levels",
        {
            "product_type": "reanalysis",
            "variable": [variable],
            "pressure_level": [str(pressure_level)],
            "year": str(year),
            "month": months,
            "day": _DAYS_ALL,
            "time": times if times is not None else _HOURS_ALL,
            "area": area,
            "data_format": "netcdf",
        },
        str(tmp_path),
    )

    dest_path = DATA_RAW / dest_name
    _extract_if_zipped(tmp_path, dest_path)

    manifest[dest_name] = {"status": "complete", "path": str(dest_path)}
    _save_manifest(manifest)

    print(f"[orchestrator] Saved: {dest_path}")
    return dest_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_client():
    os.environ["CDSAPI_RC"] = str(SECRETS)
    return cdsapi.Client()


def _extract_if_zipped(tmp_path, dest_path):
    """Move tmp_path to dest_path, unzipping ERA5-Land archives on the way."""
    if zipfile.is_zipfile(tmp_path):
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extract("data_0.nc", path=tmp_path.parent)
        extracted = tmp_path.parent / "data_0.nc"
        extracted.rename(dest_path)
        tmp_path.unlink()
    else:
        tmp_path.rename(dest_path)


def _load_manifest():
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def _save_manifest(manifest):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
