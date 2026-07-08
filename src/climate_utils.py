"""
Reusable climate-index and trend-statistics functions for the Kanto heat analysis.

Two halves:

*Index computation* lifts the Kanto spatial-reduction and threshold-count
definitions out of the exploratory notebooks (01 §3-4/§6/§8) so a single
definition is shared by every notebook rather than copy-pasted. These operate on
xarray DataArrays with ``latitude``/``longitude``/``valid_time`` coordinates.

*Trend statistics* provides the committed RQ1-RQ3 toolkit: Mann-Kendall and Sen's
slope (via ``pymannkendall``), the Pettitt change-point test (implemented here, no
extra dependency), a ``pygam`` LinearGAM helper with adjusted-R2 / residual
diagnostics, and a generic bootstrap confidence interval. These operate on plain
1-D numeric sequences (e.g. an annual area-mean series).

Analytical *narration* and figure production stay in the notebooks; this module
holds only the pure, reusable computations.

Usage
-----
    from src.climate_utils import (
        KANTO_BBOX, kanto_mean, annual_threshold_count,
        mann_kendall, sens_slope, pettitt, fit_gam, bootstrap_ci,
    )

    hot_days_grid = annual_threshold_count(daily_tmax, 35.0, months=(7, 8, 9))
    kanto_hot_days = kanto_mean(hot_days_grid)          # annual area-mean series
    mk = mann_kendall(kanto_hot_days.values)            # trend, p, Sen's slope
    cp = pettitt(kanto_hot_days.values)                 # change-point year index
"""

from __future__ import annotations

from typing import Callable, NamedTuple, Sequence

import numpy as np
import pymannkendall as mk
import xarray as xr

# ---------------------------------------------------------------------------
# Kanto bounding box
# ---------------------------------------------------------------------------
# A simple bbox, not a prefecture shapefile -- more precision isn't useful at
# ERA5-Land's 0.1-degree grid. cos(latitude) area-weighting is skipped as
# negligible over this narrow ~1.5-degree latitude band. Kept identical to the
# constants used throughout notebook 01 so the two agree by construction.
KANTO_LAT_MIN, KANTO_LAT_MAX = 35.0, 36.5
KANTO_LON_MIN, KANTO_LON_MAX = 139.0, 140.5

#: (lat_min, lat_max, lon_min, lon_max) -- convenience tuple for callers.
KANTO_BBOX = (KANTO_LAT_MIN, KANTO_LAT_MAX, KANTO_LON_MIN, KANTO_LON_MAX)


def _kanto_mask(da: xr.DataArray) -> xr.DataArray:
    """Boolean lat/lon mask selecting grid cells inside the Kanto bbox."""
    return (
        (da["latitude"] >= KANTO_LAT_MIN)
        & (da["latitude"] <= KANTO_LAT_MAX)
        & (da["longitude"] >= KANTO_LON_MIN)
        & (da["longitude"] <= KANTO_LON_MAX)
    )


def kanto_mean(da: xr.DataArray) -> xr.DataArray:
    """Spatial mean over the Kanto bbox, skipping ocean/bay NaN cells.

    Reduces a gridded field to a single value per remaining (e.g. time)
    dimension by an unweighted ``nanmean`` over the in-bbox land cells.
    """
    return da.where(_kanto_mask(da)).mean(dim=["latitude", "longitude"], skipna=True)


def kanto_exceed_fraction(da: xr.DataArray, threshold: float) -> xr.DataArray:
    """Fraction of valid (land) Kanto-bbox cells at/above *threshold*, per timestep.

    A spatial-extent metric distinct from :func:`kanto_mean`: it answers "how much
    of the box is affected" rather than "what is the box average". Returns values in
    [0, 1]; timesteps where the whole bbox is NaN yield NaN.
    """
    bbox = da.where(_kanto_mask(da))
    valid_count = bbox.notnull().sum(dim=["latitude", "longitude"])
    exceed_count = (bbox >= threshold).sum(dim=["latitude", "longitude"])
    return exceed_count / valid_count


def annual_threshold_count(
    daily: xr.DataArray,
    threshold: float,
    months: Sequence[int],
    *,
    time_dim: str = "valid_time",
) -> xr.DataArray:
    """Per-cell annual count of days at/above *threshold* within *months*.

    Filters to the given season (e.g. ``(7, 8, 9)`` for the Jul-Sep heat-wave
    window), tests ``>= threshold`` per day, and sums per calendar year. Returns a
    gridded DataArray (annual count *at each cell*) -- apply :func:`kanto_mean` to
    reduce it to the Kanto-area annual series. Reproduces the ``annual_hot_days`` /
    ``annual_tropical_nights`` definitions in notebook 01 §3-4.

    Note the ordering: threshold-then-count is applied per cell *before* any spatial
    averaging, so ``kanto_mean(annual_threshold_count(...))`` is fractional (the
    area-mean of integer per-cell counts), which is the intended RQ1 trend series.

    Water cells (all-NaN in ERA5-Land) are returned as NaN, not zero: ``NaN >=
    threshold`` evaluates False, so without re-masking they would enter downstream
    area-means as fabricated zero counts and deflate the series by the water
    fraction of the box (fixed 2026-07-08).
    """
    season = daily.sel({time_dim: daily[time_dim].dt.month.isin(list(months))})
    count = (season >= threshold).resample({time_dim: "1YE"}).sum()
    return count.where(season.notnull().any(time_dim))


# ---------------------------------------------------------------------------
# Trend statistics
# ---------------------------------------------------------------------------
class MannKendallResult(NamedTuple):
    trend: str  # "increasing" | "decreasing" | "no trend"
    p: float
    tau: float
    slope: float  # Theil-Sen (Sen's) slope, units per time step
    intercept: float


def mann_kendall(x: Sequence[float]) -> MannKendallResult:
    """Original (non-modified) Mann-Kendall trend test plus Theil-Sen slope.

    Thin wrapper over ``pymannkendall.original_test`` exposing the fields RQ1 needs.
    The ``slope`` is the Theil-Sen (Sen's) slope in units per one-year step. Input
    must be evenly spaced (annual series, one value per year, no gaps).
    """
    r = mk.original_test(np.asarray(x, dtype=float))
    return MannKendallResult(
        trend=r.trend, p=float(r.p), tau=float(r.Tau),
        slope=float(r.slope), intercept=float(r.intercept),
    )


class SensSlopeResult(NamedTuple):
    slope: float
    intercept: float
    lo: float  # bootstrap CI lower bound on slope
    hi: float  # bootstrap CI upper bound on slope


def sens_slope(
    x: Sequence[float], *, n_boot: int = 1000, ci: float = 0.95, seed: int = 0
) -> SensSlopeResult:
    """Theil-Sen slope/intercept with a bootstrap CI on the slope.

    Point estimate via ``pymannkendall.sens_slope``. The CI resamples the series
    with replacement *preserving the time index* (block-free case-resampling of
    (year, value) pairs) ``n_boot`` times -- matching the SA1-committed
    1000-resample bootstrap for time-series trend uncertainty.
    """
    x = np.asarray(x, dtype=float)
    est = mk.sens_slope(x)
    t = np.arange(len(x), dtype=float)
    rng = np.random.default_rng(seed)
    slopes = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, len(x), len(x))
        # Theil-Sen on the resampled (t, x) pairs.
        slopes[b] = _theil_sen(t[idx], x[idx])
    alpha = (1.0 - ci) / 2.0
    lo, hi = np.nanpercentile(slopes, [100 * alpha, 100 * (1 - alpha)])
    return SensSlopeResult(
        slope=float(est.slope), intercept=float(est.intercept),
        lo=float(lo), hi=float(hi),
    )


def _theil_sen(t: np.ndarray, y: np.ndarray) -> float:
    """Median of pairwise slopes; NaN if fewer than two distinct time points."""
    diffs_t = t[:, None] - t[None, :]
    diffs_y = y[:, None] - y[None, :]
    upper = np.triu_indices(len(t), k=1)
    dt = diffs_t[upper]
    dy = diffs_y[upper]
    ok = dt != 0
    if not ok.any():
        return np.nan
    return float(np.median(dy[ok] / dt[ok]))


class PettittResult(NamedTuple):
    change_index: int  # 0-based index of the last point *before* the break
    change_value: float  # the series value at change_index (for locating the year)
    K: float  # Pettitt's K statistic
    p: float  # approximate two-sided p-value


def pettitt(x: Sequence[float]) -> PettittResult:
    """Pettitt (1979) non-parametric change-point test.

    Detects a single shift in the location (median) of an ordered series without
    assuming where it is -- complementary to Mann-Kendall, which detects monotonic
    trend but can miss an abrupt regime shift (e.g. the 2002/03 East Asian jet
    change flagged in CLAUDE.md). Implemented directly (no ``pyhomogeneity``
    dependency): the statistic is a Mann-Whitney-style rank sum and the p-value uses
    the standard asymptotic approximation ``p ~ 2*exp(-6*K^2 / (n^3 + n^2))``.

    Returns the 0-based index of the last point *before* the detected break, so
    ``years[result.change_index]`` is the final year of the first regime.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    sign = np.sign(np.subtract.outer(x, x))  # sign[i, j] = sgn(x_i - x_j)
    # U_t = sum_{i<=t} sum_{j>t} sgn(x_i - x_j), for t = 0 .. n-2 (0-based split
    # after position t). The change point is argmax|U_t|.
    u = np.array([sign[: t + 1, t + 1:].sum() for t in range(n - 1)])
    k_idx = int(np.argmax(np.abs(u)))
    K = float(np.abs(u[k_idx]))
    p = 2.0 * np.exp(-6.0 * K ** 2 / (n ** 3 + n ** 2))
    return PettittResult(
        change_index=k_idx, change_value=float(x[k_idx]), K=K, p=min(p, 1.0)
    )


class GAMResult(NamedTuple):
    gam: object  # fitted pygam.LinearGAM
    x: np.ndarray  # dense predictor grid used for the fitted curve (1-D)
    fitted: np.ndarray  # gam.predict on x
    ci: np.ndarray  # (len(x), 2) response-scale confidence interval on x
    lam: float  # smoothing parameter actually used (selected, if gridsearch)
    edof: float  # effective degrees of freedom of the smooth
    aic: float  # Akaike information criterion
    gcv: float  # generalised cross-validation score
    deviance_explained: float  # fraction of null deviance explained (~R^2 for gaussian)
    pseudo_r2: float  # alias of deviance_explained (kept for call-site continuity)
    residuals: np.ndarray  # y - predict(observed x)


def fit_gam(
    x: Sequence[float],
    y: Sequence[float],
    *,
    n_splines: int = 10,
    lam: float | None = None,
    gridsearch: bool = True,
    lam_grid: Sequence[float] | None = None,
    ci_width: float = 0.95,
    n_grid: int = 200,
) -> GAMResult:
    """Fit a univariate penalised-spline LinearGAM of *y* on *x* (non-linear trend).

    The SA1-committed headline trend method. By default the smoothing parameter
    ``lam`` is selected by generalised-cross-validation gridsearch over
    ``lam_grid`` (log-spaced 1e-3..1e3 if not given) -- the bias/variance trade-off
    the RQ1 notebook makes explicit. Pass ``gridsearch=False`` with an explicit
    ``lam`` to fix the smoothing (e.g. for the under-/over-smoothed comparison, or to
    hold it constant inside a bootstrap).

    Returns the fitted model plus a dense fitted curve and its response-scale CI, and
    the diagnostics the SA1 form commits to: effective degrees of freedom, AIC, GCV,
    deviance explained, and the residuals at the observed points. ``n_splines`` is the
    basis size (upper bound on wiggliness); the penalty, not the knot count, controls
    the effective smoothness once ``lam`` is selected.
    """
    from pygam import LinearGAM, s

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    X = x.reshape(-1, 1)
    if gridsearch:
        grid = np.logspace(-3, 3, 25) if lam_grid is None else np.asarray(lam_grid)
        gam = LinearGAM(s(0, n_splines=n_splines)).gridsearch(
            X, y, lam=grid, progress=False
        )
    else:
        term = s(0, n_splines=n_splines) if lam is None else s(0, n_splines=n_splines, lam=lam)
        gam = LinearGAM(term).fit(X, y)

    xx = np.linspace(x.min(), x.max(), n_grid)
    fitted = gam.predict(xx.reshape(-1, 1))
    ci = gam.confidence_intervals(xx.reshape(-1, 1), width=ci_width)
    residuals = y - gam.predict(X)
    dev_expl = float(gam.statistics_["pseudo_r2"]["explained_deviance"])
    return GAMResult(
        gam=gam, x=xx, fitted=fitted, ci=ci,
        lam=float(np.ravel(gam.lam)[0]),
        edof=float(gam.statistics_["edof"]),
        aic=float(gam.statistics_["AIC"]),
        gcv=float(gam.statistics_["GCV"]),
        deviance_explained=dev_expl, pseudo_r2=dev_expl, residuals=residuals,
    )


def gam_derivative(gam, x_grid: Sequence[float]) -> np.ndarray:
    """First derivative of a fitted GAM's response curve over *x_grid*.

    Central finite differences of ``gam.predict`` on the (evenly spaced) grid. For an
    annual-series trend this is the *rate of change* per year -- the GAM-native
    counterpart to a Sen's slope, but allowed to vary through time, so its peak marks
    where warming is fastest (the GAM analogue of a change point).
    """
    x_grid = np.asarray(x_grid, dtype=float)
    dx = (x_grid[-1] - x_grid[0]) / (len(x_grid) - 1)
    return np.gradient(gam.predict(x_grid.reshape(-1, 1)), dx)


def bootstrap_gam(
    x: Sequence[float],
    y: Sequence[float],
    *,
    n_splines: int = 10,
    lam: float,
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 0,
    x_grid: Sequence[float] | None = None,
    derivative: bool = False,
) -> dict:
    """Case-resampling bootstrap of a fixed-``lam`` GAM fit (SA1's 1000 resamples).

    Resamples ``(x, y)`` pairs with replacement ``n_boot`` times, refits the GAM with
    the smoothing held at *lam* (the value selected on the full sample -- refitting the
    gridsearch each resample is left out for tractability, a standard bootstrap-after-
    selection simplification), and returns percentile bands of the fitted curve (and
    optionally its derivative) over ``x_grid``. This is an iid bootstrap: it does not
    model residual autocorrelation, so check the residuals-vs-year diagnostic before
    leaning on the width of the band.

    Returns a dict with ``x`` and ``fit_lo/fit_mid/fit_hi`` (and ``deriv_*`` when
    ``derivative=True``).
    """
    from pygam import LinearGAM, s

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x_grid is None:
        x_grid = np.linspace(x.min(), x.max(), 200)
    x_grid = np.asarray(x_grid, dtype=float)
    Xg = x_grid.reshape(-1, 1)
    dx = (x_grid[-1] - x_grid[0]) / (len(x_grid) - 1)
    rng = np.random.default_rng(seed)

    fits = np.empty((n_boot, len(x_grid)))
    derivs = np.empty((n_boot, len(x_grid))) if derivative else None
    for b in range(n_boot):
        idx = rng.integers(0, len(x), len(x))
        g = LinearGAM(s(0, n_splines=n_splines, lam=lam)).fit(x[idx].reshape(-1, 1), y[idx])
        pred = g.predict(Xg)
        fits[b] = pred
        if derivative:
            derivs[b] = np.gradient(pred, dx)

    q = [100 * (1 - ci) / 2, 50, 100 * (1 + ci) / 2]
    fit_lo, fit_mid, fit_hi = np.nanpercentile(fits, q, axis=0)
    out = {"x": x_grid, "fit_lo": fit_lo, "fit_mid": fit_mid, "fit_hi": fit_hi}
    if derivative:
        d_lo, d_mid, d_hi = np.nanpercentile(derivs, q, axis=0)
        out.update(deriv_lo=d_lo, deriv_mid=d_mid, deriv_hi=d_hi)
    return out


def bootstrap_ci(
    x: Sequence[float],
    stat: Callable[[np.ndarray], float],
    *,
    n_boot: int = 1000,
    ci: float = 0.95,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for an arbitrary scalar statistic of a 1-D series.

    Resamples *x* with replacement ``n_boot`` times (SA1-committed 1000 resamples by
    default), applies *stat* to each resample, and returns
    ``(point_estimate, lo, hi)`` where the point estimate is ``stat`` on the original
    series. Use for any trend/summary statistic that lacks a closed-form CI.
    """
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for b in range(n_boot):
        boots[b] = stat(x[rng.integers(0, len(x), len(x))])
    alpha = (1.0 - ci) / 2.0
    lo, hi = np.nanpercentile(boots, [100 * alpha, 100 * (1 - alpha)])
    return float(stat(x)), float(lo), float(hi)
