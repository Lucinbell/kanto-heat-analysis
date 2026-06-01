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

import datetime
import json
import os
import pathlib
import zipfile

import xarray as xr

import cdsapi
from ecmwf.datastores import Client as ECMWFClient

REPO_ROOT = pathlib.Path(__file__).parents[1]
DATA_RAW = REPO_ROOT / "data" / "raw"
DEFAULT_MANIFEST      = REPO_ROOT / "data" / "download_manifest_main.json"
DEFAULT_SHOPPING_LIST = REPO_ROOT / "data" / "download_shopping_list.json"
SECRETS = REPO_ROOT / ".secrets" / "dylan_wang.cdsapirc"

_DAYS_ALL = [f"{d:02d}" for d in range(1, 32)]
_HOURS_ALL = [f"{h:02d}:00" for h in range(24)]

_STATE_FIELDS   = ("status", "request_id", "submitted_at", "completed_at", "validated", "error")
_STATE_DEFAULTS = ("pending", None, None, None, False, None)

_CDS_FAILURE_STATUSES = {"failed", "error"}


def _pending_entry(dataset, variable, year, months, area, dest_name, **extra):
    entry = {
        "dataset":      dataset,
        "variable":     variable,
        "year":         year,
        "months":       months,
        "area":         area,
        "dest_name":    dest_name,
    }
    entry.update(extra)   # pressure_level, etc. for ERA5-PL
    for field, default in zip(_STATE_FIELDS, _STATE_DEFAULTS):
        entry[field] = default
    return entry


# ---------------------------------------------------------------------------
# Phase functions
# ---------------------------------------------------------------------------

def generate_request_manifest(
    shopping_list_path=DEFAULT_SHOPPING_LIST,
    manifest_path=DEFAULT_MANIFEST,
    force=False,
):
    """Expand a shopping list into a per-request manifest and write it to manifest_path.

    The shopping list (download_shopping_list.json) is the human-authored source of
    truth for what to download. This function resolves it into one manifest entry per
    CDS API call, respecting dataset-specific field limits (ERA5-Land: 1 variable x
    1 year per call; ERA5-PL: variable-set x pressure level x year block per call).

    Intended as a one-time authoring step — run once, review, commit both files.
    Existing manifest entries are skipped unless force=True, which resets state fields
    only (spec fields are never overwritten).
    """
    shopping_list = json.loads(pathlib.Path(shopping_list_path).read_text())
    manifest = _load_manifest(manifest_path)
    added = skipped = reset = 0

    all_specs = []

    if "era5_land" in shopping_list:
        sec = shopping_list["era5_land"]
        dataset = sec["dataset"]
        area = sec["area"]
        year_start, year_end = sec["year_range"]
        years = [str(y) for y in range(year_start, year_end + 1)]
        all_months = [f"{m:02d}" for m in range(1, 13)] if sec["months"] == "all" else sec["months"]
        block_size = sec.get("month_block_size", 1)
        month_blocks = [all_months[i:i + block_size] for i in range(0, len(all_months), block_size)]
        for var in sec["variables"]:
            for year in years:
                for block in month_blocks:
                    suffix = block[0] if block_size == 1 else f"{block[0]}_{block[-1]}"
                    dest_name = f"{var['dest_prefix']}_{year}_{suffix}.nc"
                    all_specs.append((dataset, var["variable"], year, block, area, dest_name, {}))

    if "era5_pressure_levels" in shopping_list:
        sec = shopping_list["era5_pressure_levels"]
        dataset = sec["dataset"]
        area = sec["area"]
        year_start, year_end = sec["year_range"]
        block_size = sec["year_block_size"]
        months = sec["months"]
        all_years = list(range(year_start, year_end + 1))
        blocks = [[str(y) for y in all_years[i:i + block_size]]
                  for i in range(0, len(all_years), block_size)]
        for level in sec["levels"]:
            for block in blocks:
                dest_name = f"{level['dest_prefix']}_{block[0]}_{block[-1]}.nc"
                all_specs.append((dataset, level["variable"], block, months, area, dest_name,
                                  {"pressure_level": level["pressure_level"]}))

    if "era5_single_levels" in shopping_list:
        sec = shopping_list["era5_single_levels"]
        dataset = sec["dataset"]
        area = sec["area"]
        year_start, year_end = sec["year_range"]
        block_size = sec["year_block_size"]
        months = sec["months"]
        all_years = list(range(year_start, year_end + 1))
        blocks = [[str(y) for y in all_years[i:i + block_size]]
                  for i in range(0, len(all_years), block_size)]
        for var in sec["variables"]:
            for block in blocks:
                dest_name = f"{var['dest_prefix']}_{block[0]}_{block[-1]}.nc"
                all_specs.append((dataset, var["variable"], block, months, area, dest_name, {}))

    for dataset, variable, year, months, area, dest_name, extra in all_specs:
        if dest_name in manifest:
            if force:
                for field, default in zip(_STATE_FIELDS, _STATE_DEFAULTS):
                    manifest[dest_name][field] = default
                reset += 1
            else:
                skipped += 1
            continue
        manifest[dest_name] = _pending_entry(dataset, variable, year, months, area, dest_name, **extra)
        added += 1

    _save_manifest(manifest, manifest_path)
    print(f"[orchestrator] generate_request_manifest: {added} added, {skipped} skipped, "
          f"{reset} reset → {manifest_path}")
    return manifest


def submit_pending_requests(manifest_path=DEFAULT_MANIFEST):
    """Phase 2: submit pending entries up to the CDS queue limit (5).

    CDS processes one request at a time but accepts more in the queue, so we
    keep up to 5 submitted to avoid idle gaps between completions.

    Each submission writes status→submitted, request_id, and submitted_at to the
    manifest, then saves immediately so progress survives across invocations.
    Submission failures leave status as pending and record the error string.
    """
    manifest = _load_manifest(manifest_path)
    client = _make_client()

    in_flight = sum(1 for e in manifest.values() if e.get("status") == "submitted")
    submitted = 0

    for dest_name, entry in manifest.items():
        if in_flight >= 5:
            break
        if entry.get("status") != "pending":
            continue
        try:
            request_id = _submit_request(client, entry)
            entry["status"] = "submitted"
            entry["request_id"] = request_id
            entry["submitted_at"] = datetime.datetime.now(datetime.UTC).isoformat()
            entry["error"] = None
            in_flight += 1
            submitted += 1
        except Exception as exc:
            entry["error"] = str(exc)
            print(f"[orchestrator] submit failed for {dest_name}: {exc}")
        _save_manifest(manifest, manifest_path)

    print(f"[orchestrator] submit_pending_requests: {submitted} submitted, "
          f"{in_flight} now in-flight → {manifest_path}")
    return submitted


def poll_and_download(manifest_path=DEFAULT_MANIFEST):
    """Phase 3: check submitted requests and download any that are ready.

    For each submitted entry: if results_ready, downloads to _tmp_<dest_name>,
    extracts if zipped, moves to data/raw/<dest_name>, and sets status→complete.
    CDS failures reset the entry to pending so the next run retries.
    Still-running entries are left untouched. Manifest is saved after every
    state change so progress survives across invocations.
    """
    manifest = _load_manifest(manifest_path)
    client = _make_client()

    downloaded = still_running = failed = 0

    for dest_name, entry in manifest.items():
        if entry.get("status") != "submitted":
            continue
        try:
            remote = _check_remote(client, entry["request_id"])
        except Exception as exc:
            entry["error"] = str(exc)
            print(f"[orchestrator] get_remote failed for {dest_name}: {exc}")
            _save_manifest(manifest, manifest_path)
            continue

        if remote.results_ready:
            tmp_path = DATA_RAW / f"_tmp_{dest_name}"
            dest_path = DATA_RAW / dest_name
            DATA_RAW.mkdir(parents=True, exist_ok=True)
            try:
                _download_remote(remote, tmp_path)
                _extract_if_zipped(tmp_path, dest_path)
                entry["status"] = "complete"
                entry["completed_at"] = datetime.datetime.now(datetime.UTC).isoformat()
                entry["error"] = None
                downloaded += 1
                print(f"[orchestrator] Downloaded: {dest_name}")
            except Exception as exc:
                entry["error"] = str(exc)
                print(f"[orchestrator] download failed for {dest_name}: {exc}")
            _save_manifest(manifest, manifest_path)
        elif remote.status in _CDS_FAILURE_STATUSES:
            entry["status"] = "pending"
            entry["request_id"] = None
            entry["error"] = f"CDS request failed (status: {remote.status})"
            print(f"[orchestrator] CDS failure for {dest_name} — reset to pending")
            failed += 1
            _save_manifest(manifest, manifest_path)
        else:
            still_running += 1

    print(f"[orchestrator] poll_and_download: {downloaded} downloaded, "
          f"{still_running} still running, {failed} failed → {manifest_path}")
    return downloaded


def validate_downloads(manifest_path=DEFAULT_MANIFEST):
    """Phase 4: smoke-test completed but unvalidated downloads.

    For each complete, unvalidated entry: checks file exists, size > 0, and
    xarray can open it. Sets validated=True on pass; resets to pending on fail
    so the orchestrator re-downloads on the next run. Saves after each change.
    """
    manifest = _load_manifest(manifest_path)
    validated = failed = skipped = 0

    for dest_name, entry in manifest.items():
        if entry.get("status") != "complete":
            continue
        if entry.get("validated"):
            skipped += 1
            continue

        dest_path = DATA_RAW / dest_name
        error = None

        if not dest_path.exists():
            error = "file not found"
        elif dest_path.stat().st_size == 0:
            error = "file is empty"
        else:
            try:
                xr.open_dataset(dest_path).close()
            except Exception as exc:
                error = f"xarray open failed: {exc}"

        if error is None:
            entry["validated"] = True
            validated += 1
        else:
            entry["status"] = "pending"
            entry["request_id"] = None
            entry["completed_at"] = None
            entry["validated"] = False
            entry["error"] = f"validation failed: {error}"
            print(f"[orchestrator] validation failed for {dest_name}: {error} — reset to pending")
            failed += 1
        _save_manifest(manifest, manifest_path)

    print(f"[orchestrator] validate_downloads: {validated} validated, "
          f"{failed} failed, {skipped} already validated → {manifest_path}")
    return validated


# ---------------------------------------------------------------------------
# Orchestrator entry point
# ---------------------------------------------------------------------------

def main(manifest_path=DEFAULT_MANIFEST, force_download=False):
    """Run one orchestrator cycle: submit pending requests, poll and download
    ready ones, then validate completed downloads.

    The manifest must already exist (authored via generate_request_manifest()).
    This function does not create or modify the catalogue — it only advances
    the state of existing entries.

    Parameters
    ----------
    manifest_path : path-like
        Path to the manifest JSON file.
    force_download : bool
        If True, reset all state fields on every entry before running, so the
        orchestrator re-downloads everything from scratch. Spec fields are never
        touched. Intended for reproducers who clone the repo and want to
        re-download the full dataset.
    """
    manifest_path = pathlib.Path(manifest_path)
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found: {manifest_path}\n"
            "Run generate_request_manifest() once to author it."
        )

    if force_download:
        manifest = _load_manifest(manifest_path)
        for entry in manifest.values():
            for field, default in zip(_STATE_FIELDS, _STATE_DEFAULTS):
                entry[field] = default
        _save_manifest(manifest, manifest_path)
        print(f"[orchestrator] --force-download: reset {len(manifest)} entries to pending")

    submit_pending_requests(manifest_path)
    poll_and_download(manifest_path)
    validate_downloads(manifest_path)


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

    client = _make_cdsapi_client()
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

    client = _make_cdsapi_client()
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

def _check_remote(client, request_id):
    """Reconnect to a previously submitted CDS request."""
    return client.get_remote(request_id)


def _download_remote(remote, tmp_path):
    """Download a ready CDS result to tmp_path."""
    remote.download(str(tmp_path))


def _submit_request(client, entry):
    """Submit one CDS request and return the request_id string."""
    dataset = entry["dataset"]
    variable = entry["variable"]
    if isinstance(variable, str):
        variable = [variable]

    params = {
        "variable": variable,
        "year": entry["year"],
        "month": entry["months"],
        "day": _DAYS_ALL,
        "time": _HOURS_ALL,
        "area": entry["area"],
        "data_format": "netcdf",
    }
    if dataset in ("reanalysis-era5-pressure-levels", "reanalysis-era5-single-levels"):
        params["product_type"] = "reanalysis"
    if dataset == "reanalysis-era5-pressure-levels":
        params["pressure_level"] = [str(entry["pressure_level"])]

    remote = client.submit(dataset, params)
    return remote.request_id


def _make_client():
    """Return an authenticated ecmwf-datastores-client Client."""
    lines = SECRETS.read_text().splitlines()
    url = lines[0].split(": ", 1)[1].strip()
    key = lines[1].split(": ", 1)[1].strip()
    os.environ["ECMWF_DATASTORES_URL"] = url
    os.environ["ECMWF_DATASTORES_KEY"] = key
    return ECMWFClient()


def _make_cdsapi_client():
    # TODO: remove once download_era5land / download_era5 are migrated to ecmwf-datastores-client
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


def _load_manifest(manifest_path=DEFAULT_MANIFEST):
    manifest_path = pathlib.Path(manifest_path)
    if manifest_path.exists() and manifest_path.stat().st_size > 0:
        return json.loads(manifest_path.read_text())
    return {}


def _save_manifest(manifest, manifest_path=DEFAULT_MANIFEST):
    manifest_path = pathlib.Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="CDS download orchestrator — run one cycle against a manifest."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the manifest JSON file (default: data/download_manifest_main.json)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Reset all entries to pending before running (re-downloads everything).",
    )
    args = parser.parse_args()
    main(manifest_path=args.manifest, force_download=args.force_download)
