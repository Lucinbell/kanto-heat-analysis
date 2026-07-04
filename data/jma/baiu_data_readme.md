# baiu_end_dates_1980_2025.csv — Data Notes

## Source

Japan Meteorological Agency (JMA). Historical Baiu season onset and withdrawal dates, Kanto-Koshin region (関東甲信地方), 1980–2024.

Retrieved 2026-06-01 from: https://www.data.jma.go.jp/cpd/baiu/kako_baiu09.html

The JMA table covers 1951–present and includes all regions of Japan. This file retains only the Kanto-Koshin rows for 1980–2025.

## Fields

| Field | Japanese | Description |
|---|---|---|
| `year` | 年 | Calendar year |
| `baiu_start_date` | 梅雨入り | JMA official Baiu onset date, ISO 8601 (YYYY-MM-DD) |
| `baiu_end_date` | 梅雨明け | JMA official Baiu withdrawal date, ISO 8601 (YYYY-MM-DD) |
| `baiu_precipitation_compared_to_mean_period` | 梅雨の時期の降水量の地域平均平年比(%) | Regional average precipitation during the Baiu season expressed as a percentage of the 1991–2020 climatological normal |

## Important caveats

**頃 (approximately).** All JMA Baiu onset and withdrawal dates are published with the suffix 頃 ("around" / "approximately"). This is not a data quality flag — it reflects the meteorological reality that the Baiu transition is a gradual process spanning roughly five days, not a discrete event. JMA uses the 頃 marker universally for all declared dates. Dates in this file are recorded as exact ISO dates (the day JMA cites), with the approximate nature documented here rather than encoded per-row.

**1993 — no withdrawal declaration.** JMA did not declare a Baiu withdrawal for Kanto-Koshin in 1993. The season transitioned directly into an abnormally cool, wet summer without a clear precipitation break. `baiu_end_date` is blank for this year. The precipitation ratio (144%) is still recorded; it reflects the anomalously wet conditions that year. This missing value must be handled explicitly in any model or algorithm that uses `baiu_end_date`.

**Precipitation normal period.** The `baiu_precipitation_compared_to_mean_period` values are calculated against the 1991–2020 climatological normal, per current JMA standard. Earlier JMA publications used the 1981–2010 normal; the historical table has been updated to the 1991–2020 baseline.

## Validation use

These dates are the reference series for validating any automated Baiu end date detection algorithm applied to ERA5-Land precipitation data. The algorithm output should be compared against `baiu_end_date` for years where a declaration exists (1980–2025, excluding 1993).