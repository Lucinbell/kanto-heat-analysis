# Capstone deliverables

This folder holds the final poster and the code that produced its figures.

- `SA2_poster.png` is the poster.
- `make_poster_figures.py` regenerates the three figures shown on the poster into
  `poster_figures/`, styled for A1 print (fonts sized to print at 23 cm panel
  width, poster template palette). It needs the `kanto-heat` conda environment and
  the processed data cache (`data/processed/kanto_annual_heat_indices.csv`), which
  the main analysis notebook builds on first run; raw-data download instructions
  are in `data/README.md`.

The poster figures are restyled compositions of results from the main analysis
notebook, `notebooks/04_rq1_extreme_heat_gam_v1.1.ipynb`. The model fits are
identical: the same `fit_gam` GCV-selected GAMs, the same bootstrap seeds
(11/12/13/14), and the same sustained-significance onset logic. Only the styling
and the grouping of panels differ. All fitting and bootstrap machinery lives in
`src/climate_utils.py` (`fit_gam`, `gam_derivative`, `bootstrap_gam`).

## Where each poster figure lives in the notebook


| Poster figure | Poster panel | Notebook counterpart |
|---|---|---|
| `poster_fig1_four_gam_fits.png` (2×2 grid of GAM fits) | Modelling | Sections 4.1, 4.2, 5.1, 5.2: the four single-series fit figures (`04_4-1_tmax_gam_fit`, `04_4-3_tmin_gam_fit`, `04_5-1_hot_days_gam_fit`, `04_5-3_tropical_nights_gam_fit`), each drawn by the notebook's `gam_panel` helper |
| `poster_fig2_day_night_rates.png` (day vs night warming rate) | Modelling | Sections 4.1 and 4.2: the rate-of-change figures (`04_4-2_tmax_gam_rate`, `04_4-4_tmin_gam_rate`), drawn by the `deriv_panel` helper; the derivative and bootstrap-band method is introduced in Section 3 |
| `poster_fig3_residual_diagnostics.png` (magnitude vs count residuals) | Evaluation | Section 7: the residual-diagnostics figures for the mean daily minimum (`04_7-2_residuals_magnitude_tmin`) and tropical nights (`04_7-4_residuals_count_tropical_nights`), drawn by the `residual_diagnostics` helper; the poster shows the residuals-vs-fitted and Q-Q panels of each |

The headline numbers on the poster (about 0.05 °C per year daytime,
0.14 °C per year overnight by 2024, sustained onset about 2007) come from the
Section 8 synthesis table, cached at `data/processed/rq1_gam_summary_v1.1.csv`.
