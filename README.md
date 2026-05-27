# kanto-heat-analysis

Investigation of the mechanistic drivers of Kanto surface heat extremes, tracing the causal chain from Kanto land-surface variables through Baiu monsoon termination timing, North Pacific subtropical high circulation, and terminating at Western Pacific / Indian Ocean SST forcing.

This repository hosts both the SA2 poster deliverable and the broader mechanistic investigation as a single unified codebase. The Capstone boundary is administrative, not intellectual.

---

## Research Questions

- **RQ1:** Has heat wave frequency/intensity over Kanto trended upward across the study period?
- **RQ2:** Has Baiu termination date shifted earlier, and does that trend align with the RQ1 signal?
- **RQ3:** Does earlier Baiu termination predict greater heat wave severity in the following summer (Baiu–heat coupling)?

---

## Data Access

ERA5 and ERA5-Land data are **not committed** to this repository (Copernicus licensing; file sizes).

See [`data/README.md`](data/README.md) for complete CDS API download instructions and a ready-to-run download script.

---

## Reproduction

1. Clone the repo.
2. Create the conda environment: `conda env create -f environment.yml`
3. Activate it: `conda activate kanto-heat`
4. Download data per `data/README.md`.
5. Run notebooks in order: `01_data_prep` → `07_sst_forcing`.

---

## Structure

```
kanto-heat-analysis/
├── notebooks/          # Unified analysis ordered by causal chain
├── figures/            # All outputs, tagged by source notebook
├── capstone/           # Administrative Capstone layer (poster, submission, map)
├── data/               # No data files — CDS API instructions only
├── src/                # Shared utility functions
├── references.bib      # BibTeX bibliography
└── environment.yml     # Pinned conda environment
```

See [`capstone/CAPSTONE_MAP.md`](capstone/CAPSTONE_MAP.md) for a panel-by-panel mapping of the SA2 poster to notebooks and figures.
