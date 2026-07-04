"""
Utility functions for loading JMA station daily climate records and the
official Baiu onset/withdrawal date series.

Provides infrastructure for discovering station files from the JMA master
receipt and loading them into tidy DataFrames. Analytical transformations
(seasonal indices, decade binning) belong in the calling notebook, not here.

Usage
-----
    from src.jma_data import load_station, load_stations, load_baiu_end_dates

    tokyo = load_station("tokyo")
    combined = load_stations(["tokyo", "osaka", "nagoya"])
    baiu = load_baiu_end_dates()
"""

import json
import pathlib

import pandas as pd

from .paths import REPO_ROOT

JMA_DIR = REPO_ROOT / "data" / "jma"
MASTER_RECEIPT = JMA_DIR / "master_receipt.json"

# Row indices (0-indexed) in the raw JMA obsdl export's fixed header block:
# row 0 download timestamp, row 1 blank, row 2 station name, row 3 field-group
# name, row 4 blank, row 5 quality/homogeneity/no-phenomenon sub-header,
# row 6+ data. Confirmed against the raw Tokyo/Osaka CSVs in data/jma/.
_FIELD_ROW = 3
_SUBHEAD_ROW = 5
_DATA_START_ROW = 6

# date + 4 fields x 3 sub-columns (value/quality/homogeneity), +1 extra for
# precipitation's no-phenomenon column = 1 + 3*3 + 4 = 14. Fixed by the JMA
# obsdl export format (see master_receipt.json "fields"), not per-station.
_NUM_COLUMNS = 14

_FIELD_NAME_JA = {
    "mean_temp": "平均気温(℃)",
    "max_temp": "最高気温(℃)",
    "min_temp": "最低気温(℃)",
    "precipitation": "降水量の合計(mm)",
}
_NO_PRECIP_SUBHEAD_JA = "現象なし情報"


def _locate_columns(raw: pd.DataFrame) -> dict[str, int]:
    """Map field name -> column index from the header block, not position.

    JMA's export column order is not guaranteed stable across date-range
    files for the same station: the Osaka 2005-2024 file was originally
    emitted with the precipitation block before the temperature blocks
    (fixed in place in data/jma/, .bak kept as the original). Each field's
    value column is identified as the one matching the field-group name in
    _FIELD_ROW with a blank sub-header in _SUBHEAD_ROW (the quality and
    homogeneity columns repeat the same field-group name but carry a
    sub-header label).
    """
    field_row = raw.iloc[_FIELD_ROW]
    subhead_row = raw.iloc[_SUBHEAD_ROW]

    columns = {"date": 0}
    for key, name_ja in _FIELD_NAME_JA.items():
        candidates = [
            i
            for i, (field, subhead) in enumerate(zip(field_row, subhead_row))
            if field == name_ja and pd.isna(subhead)
        ]
        assert len(candidates) == 1, f"Expected exactly one '{name_ja}' value column, found {candidates}"
        columns[key] = candidates[0]

    no_precip_candidates = [i for i, s in enumerate(subhead_row) if s == _NO_PRECIP_SUBHEAD_JA]
    assert len(no_precip_candidates) == 1, f"Expected exactly one no-phenomenon column, found {no_precip_candidates}"
    columns["no_precip_flag"] = no_precip_candidates[0]

    return columns


def station_metadata(station: str) -> dict:
    """Return the master_receipt.json metadata block for *station* (name, code, lat/lon, files)."""
    with open(MASTER_RECEIPT, encoding="utf-8") as f:
        receipt = json.load(f)
    return receipt["stations"][station]


def load_station(station: str) -> pd.DataFrame:
    """Load one JMA station's full daily record (1980-2024) as a tidy DataFrame.

    Returns columns: date, mean_temp, max_temp, min_temp, precipitation (mm),
    rained (bool). `rained` is derived from the no-phenomenon flag rather
    than `precipitation == 0`: the flag distinguishes a true zero-rain day
    (flag == 0, phenomenon occurred, precipitation reported as 0.0 due to
    trace/rounding) from a genuine no-precipitation day (flag == 1) --
    both can show `precipitation == 0`, so the raw amount alone can't tell
    them apart.
    """
    frames = []
    for file_info in station_metadata(station)["files"]:
        path = JMA_DIR / file_info["file"]
        # names= forces a fixed column count (the field-name header row is not
        # the first row, so pandas can't infer it); skip_blank_lines=False
        # keeps the two blank header rows in place so _FIELD_ROW/_SUBHEAD_ROW
        # line up with the raw file's actual row positions.
        raw = pd.read_csv(
            path,
            encoding="shift_jis",
            header=None,
            names=range(_NUM_COLUMNS),
            skip_blank_lines=False,
        )
        cols = _locate_columns(raw)
        data = raw.iloc[_DATA_START_ROW:].reset_index(drop=True)

        df = pd.DataFrame(
            {
                "date": pd.to_datetime(data[cols["date"]], format="%Y/%m/%d", errors="coerce"),
                "mean_temp": pd.to_numeric(data[cols["mean_temp"]], errors="coerce"),
                "max_temp": pd.to_numeric(data[cols["max_temp"]], errors="coerce"),
                "min_temp": pd.to_numeric(data[cols["min_temp"]], errors="coerce"),
                "precipitation": pd.to_numeric(data[cols["precipitation"]], errors="coerce"),
                "no_precip_flag": pd.to_numeric(data[cols["no_precip_flag"]], errors="coerce"),
            }
        )
        # Drops the trailing footer row (a blank, whitespace-padded line JMA
        # appends after the last data row) along with any other unparsed rows.
        df = df.dropna(subset=["date"])
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
    combined["rained"] = combined["no_precip_flag"] == 0
    return combined.drop(columns="no_precip_flag")


def load_stations(stations: list[str]) -> pd.DataFrame:
    """Load and concatenate multiple stations into one tidy DataFrame with a `station` column."""
    frames = []
    for station in stations:
        df = load_station(station)
        df.insert(0, "station", station)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


BAIU_END_DATES_FILE = JMA_DIR / "baiu_end_dates_1980_2025.csv"


def load_baiu_end_dates() -> pd.DataFrame:
    """Load JMA's official Baiu onset/withdrawal dates for Kanto-Koshin (1980-2025).

    Returns columns: year, baiu_start_date, baiu_end_date (datetime64; NaT for
    1993, the one year JMA declared no withdrawal), precip_ratio (% of the
    1991-2020 climatological normal), season_length_days (NaN for 1993). See
    data/jma/baiu_data_readme.md for source and caveats -- these are the
    reference dates RQ2/RQ3 validate any automated detection algorithm against.
    """
    df = pd.read_csv(BAIU_END_DATES_FILE)
    df["baiu_start_date"] = pd.to_datetime(df["baiu_start_date"])
    df["baiu_end_date"] = pd.to_datetime(df["baiu_end_date"])
    df = df.rename(columns={"baiu_precipitation_compared_to_mean_period": "precip_ratio"})
    df["season_length_days"] = (df["baiu_end_date"] - df["baiu_start_date"]).dt.days
    return df
