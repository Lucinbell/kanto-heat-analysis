# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context

University of Leeds MSc Data Science capstone (OLDA5302M, Cohort J02 2025/26). The research quantifies long-term changes in the summer climate of the Kanto Metropolitan Area, Japan (1980–2024), by analysing the Baiu rainy season and post-Baiu heat wave season as coupled expressions of the East Asian Summer Monsoon, using ERA5-Land reanalysis data.

**Three research questions (committed in SA1 planning form):**
- **RQ1:** How have extreme heat event frequencies (≥35°C days, ≥25°C tropical nights) changed in Kanto, 1980–2024?
- **RQ2:** How has the seasonal timing and intensity of the Baiu rainy season shifted over the same period?
- **RQ3:** Does an earlier Baiu end date predict a more extreme subsequent heat wave season?

## Environment

```bash
conda env create -f environment.yml
conda activate kanto-heat
jupyter lab
```

Pin package versions in `environment.yml` at the time of addition — not retroactively.

Conda is not on the system PATH — use Anaconda Prompt or call `conda.exe` directly via `CONDA_ROOT` in `.local_env`. The `kanto-heat` Jupyter kernel should be registered; if it does not appear, re-register with `python -m ipykernel install --user --name kanto-heat`. Machine-specific paths are in `.local_env` (gitignored — each contributor maintains their own copy). For current environment setup status, check the KHA Jira board.

Create `.local_env` at the repo root with your own paths:
```
CONDA_ROOT=C:\Users\<you>\anaconda3
CONDA_ENV_PATH=C:\Users\<you>\anaconda3\envs\kanto-heat
JUPYTER_KERNEL_PATH=C:\Users\<you>\AppData\Roaming\jupyter\kernels\kanto-heat
```

## Repository Design Principles

- **Kanto-first discipline.** Every analytical layer traces mechanistic steps backward from the Kanto surface heat signal. Upstream layers (circulation, SST) are only pursued to the extent they explain variance in the layer below.
- **No data files committed.** ERA5 files are too large and subject to Copernicus licensing. `data/README.md` contains CDS API download instructions.
- **`src/` for reusable code.** `climate_utils.py` holds shared functions (Mann-Kendall, Sen's slope, Baiu end date algorithm, index computation). `cds_orchestrator.py` is infrastructure, not analysis — keep it out of notebooks.
- **`capstone/CAPSTONE_MAP.md` is written last.** Write it only after the analysis is finalised; figure filenames must reflect the final state.

## Committed Methodology (SA1 Planning Form)

These techniques were committed to in the submitted Assessment 1. They may evolve as the analysis unfolds but are the baseline to deviate from intentionally, not casually.

| Technique | Purpose |
|---|---|
| Generalised Additive Model (GAM) | Non-linear trend estimation for temperature and Baiu seasonal totals |
| Zero-inflated Gamma model | Two-part precipitation model (Bernoulli occurrence + Gamma intensity) — required to handle zero-inflation; omitting this would bias intensity estimates |
| Linear regression / Pearson correlation | Testing the Baiu end date coupling hypothesis (RQ3) |

**Seasonal windows:** Baiu season = June 1–July 31; heat wave season = July 1–September 30.
**Thresholds:** extreme-heat day ≥35°C; tropical night ≥25°C overnight.
**Evaluation:** GAM assessed via adjusted R² and residual diagnostics. All time-series models use bootstrap CI (1000 resamples). RQ3 coupling confirmed via permutation test (n=10,000).
**Feasibility validation step:** Replicate 1980–2010 mean Baiu onset date against published JMA values before proceeding with full analysis.

GEV distribution for return-period estimation was not committed to in SA1 — apply only if analytically justified.

## Key Analytical Decisions

- **Mann-Kendall + Pettitt together.** The 2002/2003 East Asian jet regime shift falls within the study period — a structural break Mann-Kendall alone may miss. Run both tests; let Pettitt identify the break date rather than imposing 2003 from prior literature. The GAM naturally captures the non-linear trajectory. Do not report a single linear trend across the full period.
- **Niño 3.4 covariate in RQ3.** ENSO independently modulates both Baiu timing and heat wave severity, creating a confounding problem. Use multiple regression with Niño 3.4 as covariate; confirm the Baiu–heat signal survives exclusion of strong ENSO years. Frame RQ3 as a hypothesis to be tested, not an established relationship.
- **Baiu trend is likely non-monotonic.** East Asian Summer Monsoon trends show non-monotonic behaviour across the study period. Expect and report a non-linear GAM trajectory — not a single slope.

## Causal Language Rules

The ERA5 analysis documents observed trends and tests statistical associations — it cannot attribute those trends to specific forcing given the multi-ocean, ENSO-modulated nature of the system.

| Avoid | Use instead |
|---|---|
| "Rising SSTs cause the NPSH to strengthen" | "Consistent with documented WNPSH intensification under Indo-Pacific SST warming" |
| "Earlier Baiu termination causes more extreme heat" | "Earlier Baiu termination is associated with more extreme subsequent heat wave seasons" |
| "The trend is linear / monotonic" | "The GAM fit reveals a non-linear trajectory, with [describe shape]" |
| Citing Francis & Vavrus (Arctic amplification) without Blackport & Screen (2020) as counterpoint | Always pair them |

**Do not include Arctic amplification in the mechanistic causal chain.** The literature does not support it for Japan summer heat waves; it may appear as contested background context only.

## Data

**No data files are committed.** All raw data lives in `data/raw/` (gitignored) and processed outputs in `data/processed/` (gitignored).

**CDS API field limit (ERA5-Land):** 12,000 fields per request. One variable + one year ≈ 8,760 fields — safe. Never combine two variables in one ERA5-Land call (exceeds the limit). Strategy: 1 variable × 1 year per call.

**ERA5-Land vs ERA5:** Use ERA5-Land for Kanto surface variables (2m temperature, precipitation, soil moisture). Use ERA5 proper for pressure-level circulation indices (500 hPa, 200 hPa, 850 hPa) — ERA5-Land does not include pressure levels.

File naming convention:
```
data/raw/
  era5land_2m_temperature_1980.nc
  era5land_total_precipitation_1980.nc
  era5_circulation_JJA_1980_1989.nc

data/processed/
  kanto_daily_tmax_1980_2024.csv
  kanto_daily_precip_1980_2024.csv
  baiu_end_dates_1980_2024.csv    # Manually compiled from JMA
```

`src/cds_orchestrator.py` manages stateful, idempotent bulk downloads via a manifest at `data/download_manifest.json`. It is safe to re-run at any point.

**Credentials:** stored at `.secrets/{user_name}.cdsapirc` (gitignored). Point cdsapi at it via `os.environ["CDSAPI_RC"] = str(secrets_path)` — do not copy to `~/.cdsapirc`.

## SA2 Scope Boundary

The notebook sequence is ordered bottom-up along the mechanistic causal chain (Kanto surface → upstream SST forcing) and treated as a soft roadmap — sequencing may shift as the analysis unfolds. Notebooks covering Kanto heat, Baiu timing, and Baiu–heat coupling are **SA2 core**. Notebooks covering large-scale circulation indices and SST forcing are **addendum** (GitHub only, not assessed).

## Session Folders

At the start of each work session, create a session folder at `sandbox\YYYY-MM-DD-[NN]-[topic]\`:
- `YYYY-MM-DD` is the date the session started
- `[NN]` is the zero-indexed session count for that day (00, 01, …)
- `[topic]` is a short, concise description — use the user's supplied name if given, otherwise judge from the work

Each session folder must contain a `README.md` covering: objective, plan, and what was done. The folder is a local draft station for temporary artifacts (memos, test scripts, scratch `.ipynb` files). Session folders are gitignored and never committed.

## Project Documentation & Tracking

**Confluence** (space `GP` at `lucinbell.atlassian.net`) is the central repository for memos, notes, and project documentation. When the user says "check Confluence", start from the top page (ID 289308674) and navigate from there.

**Jira** (project `KHA` at `lucinbell.atlassian.net`) is the task kanban. When the user says "check my kanban", look there. Epic structure: KHA-1 (Setup) → KHA-2 (Data) → KHA-3 (EDA) → KHA-4 (Modelling) → KHA-5 (Addendum) → KHA-6 (SA2 deliverable).

**Bibliography:** All references in `references.bib` (BibTeX). Priority literature documented in the Mechanistic Model Confluence page.

## AI Usage

AI assistance is Amber category per OLDA5302M guidelines. The full charter is documented in `README.md`. The operative constraint for Claude Code is:

- **Write freely:** git operations, repo infrastructure, data download orchestration, utility scaffolding, documentation
- **Do not write:** analytical code — statistical models, data transformations, index computations, visualisations that embody the research. For analytical work, act as technical advisor only: explain, debug code the author has written, suggest approaches for the author to evaluate and implement
- **Do not generate:** research framing, conclusions, or poster narrative. Help sharpen and articulate what the author has drafted
