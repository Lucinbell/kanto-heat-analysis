# Data Access

No ERA5 / ERA5-Land data files are committed to this repository — Copernicus licensing and file size both rule it out. This document explains how to reproduce `data/raw/` from scratch via the CDS API, and what's already committed vs. gitignored.

## What's committed vs. gitignored

```
data/
├── README.md                          # this file — committed
├── download_shopping_list.json        # human-authored download spec — committed
├── download_manifest_main.json        # generated per-request manifest + state — committed
├── raw/                                # gitignored — CDS downloads land here
├── processed/                          # gitignored — derived NetCDF/CSV outputs
└── jma/
    ├── master_receipt.json             # committed — station metadata
    ├── baiu_end_dates_1980_2025.csv    # committed — JMA reference Baiu dates
    ├── baiu_data_readme.md             # committed — source/caveats for the above
    └── *.csv                           # raw per-station JMA exports — gitignored
```

The JMA files are small, manually-curated reference data (not ERA5 downloads, no licensing restriction), so they're committed directly — no download step needed for them. See `data/jma/baiu_data_readme.md` for their provenance. The raw per-station JMA CSVs are excluded because they were downloaded manually from the JMA obsdl portal and aren't part of the reproducible pipeline; get them via `src/jma_data.py`'s expectations or re-export from https://www.data.jma.go.jp/risk/obsdl/ if starting fresh.

Everything below concerns `data/raw/` (ERA5 / ERA5-Land) and `data/processed/`.

## 1. Get CDS API credentials

1. Register at https://cds.climate.copernicus.eu and accept the ERA5/ERA5-Land licence terms on the dataset pages you'll use:
   - https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land
   - https://cds.climate.copernicus.eu/datasets/reanalysis-era5-pressure-levels
   - https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels
2. Copy your API key from your CDS profile page.
3. Create `.secrets/<your_name>.cdsapirc` at the repo root (this directory is gitignored) with:
   ```
   url: https://cds.climate.copernicus.eu/api
   key: <your-api-key>
   ```
4. Point `src/cds_orchestrator.py`'s `SECRETS` constant at your file (currently hardcoded to `.secrets/dylan_wang.cdsapirc` — update to your own filename if reproducing on another machine).

`_make_client()` / `_make_cdsapi_client()` in `src/cds_orchestrator.py` read this file and set `ECMWF_DATASTORES_URL` / `ECMWF_DATASTORES_KEY` (or `CDSAPI_RC`) from it — never copy credentials to `~/.cdsapirc`.

## 2. Understand the two datasets

| | ERA5-Land | ERA5 (pressure levels / single levels) |
|---|---|---|
| Use for | Kanto surface variables: 2m temperature, precipitation, soil moisture | Circulation indices: geopotential height, wind components, MSLP at 500/850/200 hPa |
| Resolution | ~9 km | ~31 km |
| Field limit | 12,000 fields/request. One variable × one year × all hours ≈ 8,760 fields — safe. **Never combine two variables in one ERA5-Land call.** | Same limit; the shopping list blocks by year instead of month to stay under it |

## 3. Author the download manifest (one-time)

`data/download_shopping_list.json` is the human-authored source of truth for what to download — variables, year ranges, bounding boxes, priorities. It's already populated for this project (Kanto area `[38, 133, 33, 142]` for ERA5-Land; wider East Asia domain `[80, 100, 10, 180]` for circulation variables, JJAS months only).

To (re)generate the per-request manifest from it:

```python
from src.cds_orchestrator import generate_request_manifest
generate_request_manifest()   # writes/updates data/download_manifest_main.json
```

This expands the shopping list into one manifest entry per CDS API call (respecting the field limits above) and is idempotent — existing entries are left alone unless `force=True`. `data/download_manifest_main.json` is committed so the *catalogue* of what's being tracked is visible, even though the actual `.nc`/`.grib` files it points to under `data/raw/` are not.

## 4. Run the orchestrator

The orchestrator is stateful and safe to re-run at any point — it picks up wherever the manifest left off:

```bash
python -m src.cds_orchestrator
```

Each cycle:
1. **Submits** up to 5 pending requests to the CDS queue (CDS processes one at a time but accepts more in-flight).
2. **Polls** submitted requests; downloads any that are ready to `data/raw/`, unzipping ERA5-Land archives and converting GRIB → NetCDF where needed.
3. **Validates** completed downloads (file exists, non-empty, opens cleanly with `xarray`); failed validation resets the entry to `pending` so it's retried automatically.

Because a full 1980–2024 download spans many CDS requests (each can take minutes to hours to process in the CDS queue), expect to run this command repeatedly (e.g. every 30–60 minutes, or on a schedule) until all manifest entries reach `status: complete, validated: true`. Check progress with:

```python
import json
manifest = json.load(open("data/download_manifest_main.json"))
from collections import Counter
print(Counter(e["status"] for e in manifest.values()))
```

To force a full re-download from scratch (e.g. after cloning the repo with an empty `data/raw/`):

```bash
python -m src.cds_orchestrator --force-download
```

This resets all manifest entries' state fields to `pending` — it does not touch the shopping list or the request specs, so nothing needs re-authoring.

## 5. One-off downloads

For ad-hoc pulls outside the shopping-list/manifest workflow, use the public functions directly:

```python
from src.cds_orchestrator import download_era5land, download_era5

download_era5land(
    variable="2m_temperature",
    year="2023",
    months=["06", "07", "08"],
    area=[38, 133, 33, 142],          # [N, W, S, E]
    dest_name="era5land_2m_temperature_2023_06_08.nc",
)

download_era5(
    variable="geopotential",
    year="2023",
    months=["07"],
    pressure_level="500",
    area=[80, 100, 10, 180],
    dest_name="era5_geopotential_500hPa_2023_07.nc",
)
```

These also check `data/download_manifest_main.json` and skip already-complete entries, but they run synchronously (blocking on the CDS queue) rather than via the submit/poll cycle — fine for a single file, impractical for the full historical range.

## 6. Where downloads end up

Files land in `data/raw/` (or wherever `.local_env`'s `DATA_RAW_DIR` points — see `src/paths.py`), named per the shopping list's `dest_prefix`, e.g.:

```
data/raw/
  era5land_2m_temperature_1980_01.nc
  era5land_total_precipitation_1980_01.nc
  era5pl_geopotential_500hPa_1980_1988.nc
```

Notebooks should read from these via `src.paths.RAW_DIR`, not hardcoded paths. Derived, reusable outputs (e.g. Kanto-averaged daily series) belong in `data/processed/`, cached as NetCDF/CSV rather than recomputed on every notebook run (see the check-then-compute pattern used in `notebooks/01_cds_data_exploration.ipynb`).
