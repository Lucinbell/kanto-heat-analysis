"""Generate the three figures on the poster (SA2_poster.png in this folder).

Outputs to capstone/poster_figures/ at print resolution: each figure is sized to
print 1:1 at its 23 cm poster panel width (figsize width 9.06 in, 300 dpi).
Palette matches the poster template: navy #174273 (series), charcoal #39464D
(ink and data points), pale blue #D1D9E3 (bands and grid).

The underlying fits are identical to the main analysis notebook
(notebooks/04_rq1_extreme_heat_gam_v1.1.ipynb): same fit_gam GCV selection,
same bootstrap seeds (11/12/13/14). Only styling and panel composition differ.
See README.md in this folder for the figure-by-figure mapping.

Requires the kanto-heat conda env and the processed data cache
(data/processed/kanto_annual_heat_indices.csv, built by the main notebook).
"""
import pathlib
import sys

import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats as sp_stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.climate_utils import bootstrap_gam, fit_gam, gam_derivative  # noqa: E402

OUT = pathlib.Path(__file__).parent / "poster_figures"
OUT.mkdir(exist_ok=True)

NAVY, CHARCOAL, PALE = "#174273", "#39464D", "#D1D9E3"

plt.rcParams.update({
    "font.family": "Arial",
    "font.size": 13,
    "text.color": CHARCOAL,
    "axes.edgecolor": CHARCOAL,
    "axes.labelcolor": CHARCOAL,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "axes.titlecolor": NAVY,
    "axes.labelsize": 13.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.color": CHARCOAL,
    "ytick.color": CHARCOAL,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "axes.grid": True,
    "grid.color": PALE,
    "grid.linewidth": 0.9,
    "legend.fontsize": 12.5,
    "legend.frameon": False,
})

heat = pd.read_csv(ROOT / "data/processed/kanto_annual_heat_indices.csv", index_col="year")
years = heat.index.values.astype(float)

series = {
    "summer_tmax_mean_c": ("Mean daily maximum", "°C", 11, False),
    "summer_tmin_mean_c": ("Mean daily minimum", "°C", 12, True),
    "hot_days_ge33": ("Hot days (max ≥33 °C)", "days per year", 13, False),
    "tropical_nights_ge25": ("Tropical nights (min ≥25 °C)", "nights per year", 14, True),
}
gams, boots = {}, {}
for k, (_, _, seed, _) in series.items():
    g = fit_gam(years, heat[k].values)
    gams[k] = g
    boots[k] = bootstrap_gam(years, heat[k].values, lam=g.lam, n_boot=1000,
                             seed=seed, x_grid=g.x, derivative=True)


def onset(k):
    """Start year of the sustained significant-positive rate run reaching 2024."""
    sig = boots[k]["deriv_lo"] > 0
    if not sig[-1]:
        return None
    i = len(sig) - 1
    while i > 0 and sig[i - 1]:
        i -= 1
    return gams[k].x[i]


# --- Figure 1: four GAM fits (2x2), Modelling panel --------------------------
fig, axes = plt.subplots(2, 2, figsize=(9.06, 5.9), constrained_layout=True)
order = ["summer_tmax_mean_c", "summer_tmin_mean_c", "hot_days_ge33", "tropical_nights_ge25"]
for ax, k in zip(axes.flat, order):
    label, unit, _, night = series[k]
    g = gams[k]
    h_pts = ax.plot(years, heat[k].values, "o", color=CHARCOAL, ms=3.6, alpha=0.55, zorder=2)[0]
    h_ci = ax.fill_between(g.x, g.ci[:, 0], g.ci[:, 1], color=PALE, zorder=1)
    h_fit = ax.plot(g.x, g.fitted, color=NAVY, lw=2.8, zorder=3)[0]
    o = onset(k)
    if night and o is not None:
        ax.axvline(o, color=CHARCOAL, ls=":", lw=1.6)
        ax.text(o - 1.2, ax.get_ylim()[1], f"rise sustained\nfrom {o:.0f}", ha="right",
                va="top", fontsize=11.5, color=CHARCOAL)
    ax.set_title(label)
    ax.set_ylabel(unit)
fig.legend([h_pts, h_fit, h_ci], ["Annual value (ERA5-Land Kanto area-mean)",
           "GAM smooth", "95% confidence band"],
           loc="upper center", bbox_to_anchor=(0.5, 1.09), ncol=3)
fig.savefig(OUT / "poster_fig1_four_gam_fits.png", dpi=300, bbox_inches="tight",
            facecolor="white")
plt.close(fig)

# --- Figure 2: day vs night warming rate (1x2, shared y), Modelling panel ----
fig, axes = plt.subplots(1, 2, figsize=(9.06, 3.4), sharey=True, constrained_layout=True)
for ax, k, title in [
    (axes[0], "summer_tmax_mean_c", "Daytime: steady"),
    (axes[1], "summer_tmin_mean_c", "Overnight: accelerating"),
]:
    g, b = gams[k], boots[k]
    d = gam_derivative(g.gam, g.x)
    ax.fill_between(g.x, b["deriv_lo"], b["deriv_hi"], color=PALE)
    ax.plot(g.x, d, color=NAVY, lw=2.8)
    ax.axhline(0, color=CHARCOAL, lw=1.0)
    o = onset(k)
    if k == "summer_tmin_mean_c" and o is not None:
        ax.axvline(o, color=CHARCOAL, ls=":", lw=1.6)
        ax.text(o - 1.2, 0.185, f"sustained rise\nfrom {o:.0f}", ha="right", va="top",
                fontsize=11.5, color=CHARCOAL)
    ax.set_title(title)
axes[0].set_ylabel("Warming rate (°C per year)")
axes[0].set_ylim(-0.06, 0.20)
fig.savefig(OUT / "poster_fig2_day_night_rates.png", dpi=300, bbox_inches="tight",
            facecolor="white")
plt.close(fig)

# --- Figure 3: residual diagnostics, magnitude vs count (2x2), Evaluation ----
fig, axes = plt.subplots(2, 2, figsize=(9.06, 4.35), constrained_layout=True)
for row, k, kind in [
    (0, "summer_tmin_mean_c", "Magnitude"),
    (1, "tropical_nights_ge25", "Count"),
]:
    g = gams[k]
    resid = g.residuals
    fitted_obs = heat[k].values - resid
    ax = axes[row, 0]
    ax.scatter(fitted_obs, resid, color=CHARCOAL, s=16, alpha=0.6)
    ax.axhline(0, color=CHARCOAL, lw=1.0)
    ax.set_title(f"{kind}: residuals vs fitted")
    ax.set_ylabel("Residual")
    if row == 1:
        ax.set_xlabel("Fitted value")
    ax = axes[row, 1]
    sp_stats.probplot(resid, plot=ax)
    pts, line = ax.get_lines()
    pts.set(color=CHARCOAL, marker="o", markersize=4, alpha=0.6, linestyle="none")
    line.set(color=NAVY, lw=2.2)
    ax.set_title(f"{kind}: normal Q-Q")
    ax.set_ylabel("Ordered residuals")
    ax.set_xlabel("Theoretical quantiles" if row == 1 else "")
fig.savefig(OUT / "poster_fig3_residual_diagnostics.png", dpi=300, bbox_inches="tight",
            facecolor="white")
plt.close(fig)

for p in sorted(OUT.glob("poster_fig*.png")):
    print(p.name, f"{p.stat().st_size/1024:.0f} KB")
print("done")
