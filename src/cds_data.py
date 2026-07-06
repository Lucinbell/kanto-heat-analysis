"""
Utility functions for loading ERA5 CDS data from the download manifest.

Provides infrastructure for discovering validated files and opening them as a
single lazy xarray Dataset via Dask. Analytical transformations (aggregation,
index computation) belong in the calling notebook, not here.

Covers both ERA5-Land (manifest ``variable`` is a plain string, e.g.
``"2m_temperature"``) and ERA5 pressure-level data (``variable`` is a one-item
list plus a separate ``pressure_level`` field, e.g. geopotential at 500 hPa).

Usage
-----
    from src.cds_data import open_era5land, open_era5_pressure_level

    ds = open_era5land("2m_temperature")
    # ds is lazy — no data loaded until compute() or a reduction is called

    ds_z500 = open_era5_pressure_level("geopotential", "500")
"""

import json
import pathlib

import xarray as xr

from .paths import RAW_DIR, REPO_ROOT

DEFAULT_MANIFEST = REPO_ROOT / "data" / "download_manifest_main.json"

_CHUNK_DEFAULTS = {"time": 744}  # ~1 month of hourly data


def manifest_paths(
    variable: str,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST,
    raw_dir: pathlib.Path = RAW_DIR,
) -> list[pathlib.Path]:
    """Return sorted file paths for *variable* from the manifest.

    Only entries with status='complete' and validated=True are included,
    so partial or failed downloads are never surfaced to callers.
    """
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    paths = [
        raw_dir / entry["dest_name"]
        for entry in manifest.values()
        if entry.get("variable") == variable
        and entry.get("status") == "complete"
        and entry.get("validated") is True
    ]

    if not paths:
        raise FileNotFoundError(
            f"No complete validated files found for variable '{variable}' "
            f"in manifest: {manifest_path}"
        )

    return sorted(paths)


def open_era5land(
    variable: str,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST,
    raw_dir: pathlib.Path = RAW_DIR,
    chunks: dict | None = None,
) -> xr.Dataset:
    """Open all ERA5-Land files for *variable* as a single lazy Dataset.

    Files are discovered from the manifest (complete + validated only),
    sorted by filename (which is chronological given the naming convention),
    and concatenated along the time axis via open_mfdataset.

    Parameters
    ----------
    variable:
        CDS variable name, e.g. ``"2m_temperature"``.
    manifest_path:
        Path to the download manifest JSON. Defaults to
        ``data/download_manifest_main.json``.
    raw_dir:
        Directory containing the .nc files. Defaults to ``data/raw/``.
    chunks:
        Dask chunk sizes. Defaults to ``{"time": 744}`` (~1 month hourly).
        Pass an explicit dict to override, e.g. ``{"time": 24}`` for
        day-at-a-time processing.

    Returns
    -------
    xr.Dataset
        Lazy dataset. No data is loaded until ``.compute()`` or a
        reduction is triggered.
    """
    if chunks is None:
        chunks = _CHUNK_DEFAULTS

    paths = manifest_paths(variable, manifest_path, raw_dir)

    return xr.open_mfdataset(
        paths,
        combine="by_coords",
        chunks=chunks,
        engine="netcdf4",
    )


def manifest_paths_pressure_level(
    variable: str,
    pressure_level: str,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST,
    raw_dir: pathlib.Path = RAW_DIR,
) -> list[pathlib.Path]:
    """Return sorted file paths for a pressure-level *variable* at *pressure_level*.

    Pressure-level manifest entries store ``variable`` as a one-item list (not a
    plain string like ERA5-Land entries) and carry a separate ``pressure_level``
    field, so this mirrors ``manifest_paths`` with that lookup shape instead.

    Only entries with status='complete' and validated=True are included, so
    partial or failed downloads are never surfaced to callers.
    """
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    paths = [
        raw_dir / entry["dest_name"]
        for entry in manifest.values()
        if entry.get("variable") == [variable]
        and entry.get("pressure_level") == pressure_level
        and entry.get("status") == "complete"
        and entry.get("validated") is True
    ]

    if not paths:
        raise FileNotFoundError(
            f"No complete validated files found for variable '{variable}' at "
            f"pressure_level '{pressure_level}' in manifest: {manifest_path}"
        )

    return sorted(paths)


def open_era5_pressure_level(
    variable: str,
    pressure_level: str,
    manifest_path: pathlib.Path = DEFAULT_MANIFEST,
    raw_dir: pathlib.Path = RAW_DIR,
    chunks: dict | None = None,
    preprocess=None,
) -> xr.Dataset:
    """Open all ERA5 pressure-level files for *variable* at *pressure_level*.

    Files are discovered from the manifest (complete + validated only),
    sorted by filename (chronological given the naming convention), and
    concatenated along the time axis via open_mfdataset.

    Parameters
    ----------
    variable:
        CDS variable name, e.g. ``"geopotential"``.
    pressure_level:
        Pressure level in hPa as stored in the manifest, e.g. ``"500"``.
    manifest_path:
        Path to the download manifest JSON. Defaults to
        ``data/download_manifest_main.json``.
    raw_dir:
        Directory containing the .nc files. Defaults to ``data/raw/``.
    chunks:
        Dask chunk sizes. Defaults to ``{"time": 744}`` (~1 month hourly).
    preprocess:
        Optional callable applied to each file's Dataset before concatenation
        (e.g. a spatial ``.sel()`` subset), passed through to
        ``open_mfdataset``. Pressure-level files cover a much larger domain
        (100-180E x 10-80N) than most analyses need, so subsetting here keeps
        downstream resampling cheap.

    Returns
    -------
    xr.Dataset
        Lazy dataset. No data is loaded until ``.compute()`` or a
        reduction is triggered.
    """
    if chunks is None:
        chunks = _CHUNK_DEFAULTS

    paths = manifest_paths_pressure_level(variable, pressure_level, manifest_path, raw_dir)

    return xr.open_mfdataset(
        paths,
        combine="by_coords",
        chunks=chunks,
        engine="netcdf4",
        preprocess=preprocess,
    )
