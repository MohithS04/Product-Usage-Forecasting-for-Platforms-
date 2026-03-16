"""
model.py
========
Core product-usage forecasting model for GitLab Platform sections.

Architecture
------------
The model uses a *Trend + Seasonality + Residual* decomposition approach:

1. **Trend** – Weighted least-squares linear regression fit to historical
   monthly averages.  Recent months receive higher weight so the model adapts
   quickly to usage shifts.
2. **Seasonality** – Month-of-year indices derived from 24 months of history.
3. **Residuals** – Gaussian noise band used to compute 95 % prediction intervals.

Target accuracy: ≥ 95 % (measured as 100 - MAPE across active_users, cpu_pct,
memory_gb, api_calls).

Usage
-----
    from forecasting.model import UsageForecaster

    forecaster = UsageForecaster()
    forecaster.fit(monthly_df)          # pandas DataFrame (see load_monthly_data)
    forecast_df = forecaster.predict(horizon=3)
    print(forecast_df)
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SectionModel:
    """Trained parameters for a single platform section."""

    section_name: str
    metric_col: str
    slope: float = 0.0
    intercept: float = 0.0
    seasonal_indices: Dict[int, float] = field(default_factory=dict)   # month -> index
    residual_std: float = 0.0
    n_obs: int = 0
    last_t: int = 0                  # max time index seen during training
    last_month: str = ""             # YYYY-MM of the most recent observation
    log_space: bool = False          # whether fit was performed in log-space


@dataclass
class ForecastPoint:
    """One month-ahead forecast for a single metric."""

    section_name: str
    forecast_month: str
    metric: str
    predicted: float
    ci_lower: float
    ci_upper: float


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

_METRICS = ["active_users", "cpu_usage_pct", "memory_usage_gb", "api_calls"]

# Metrics with exponential growth – fitted in log-space for higher accuracy.
_LOG_SPACE_METRICS = {"active_users", "api_calls", "memory_usage_gb"}


def _weighted_linreg(
    t: np.ndarray, y: np.ndarray, weights: Optional[np.ndarray] = None
) -> Tuple[float, float]:
    """Weighted least-squares for y = intercept + slope * t."""
    if weights is None:
        weights = np.ones(len(t))
    W = np.diag(weights)
    X = np.column_stack([np.ones(len(t)), t])
    try:
        coeffs = np.linalg.lstsq(W @ X, W @ y, rcond=None)[0]
    except np.linalg.LinAlgError:
        coeffs = np.array([y.mean(), 0.0])
    return float(coeffs[0]), float(coeffs[1])   # intercept, slope


def _seasonal_indices(months: np.ndarray, values: np.ndarray) -> Dict[int, float]:
    """
    Compute month-of-year multiplicative seasonal indices.
    Index 1.0 means average; >1 above-average, <1 below-average.

    Uses a Fourier (sinusoidal) regression to smooth the seasonal curve,
    which is more robust than raw monthly averages when each month appears
    only once or twice in the training set.
    """
    overall_mean = values.mean()
    if overall_mean == 0:
        return {m: 1.0 for m in range(1, 13)}

    # Fit a 2-harmonic Fourier model: a0 + a1*cos(2pi*t/12) + b1*sin(2pi*t/12)
    #                                    + a2*cos(4pi*t/12) + b2*sin(4pi*t/12)
    t = months.astype(float)
    X = np.column_stack([
        np.ones(len(t)),
        np.cos(2 * np.pi * t / 12),
        np.sin(2 * np.pi * t / 12),
        np.cos(4 * np.pi * t / 12),
        np.sin(4 * np.pi * t / 12),
    ])
    y_norm = values / overall_mean   # normalise to seasonal indices ≈ 1.0

    try:
        coeffs = np.linalg.lstsq(X, y_norm, rcond=None)[0]
    except np.linalg.LinAlgError:
        coeffs = np.array([1.0, 0.0, 0.0, 0.0, 0.0])

    indices: Dict[int, float] = {}
    for m in range(1, 13):
        xm = np.array([
            1.0,
            math.cos(2 * math.pi * m / 12),
            math.sin(2 * math.pi * m / 12),
            math.cos(4 * math.pi * m / 12),
            math.sin(4 * math.pi * m / 12),
        ])
        idx = float(xm @ coeffs)
        # Clamp to a reasonable range
        indices[m] = max(0.5, min(2.0, idx))
    return indices


def _add_months(year_month: str, n: int) -> str:
    """Add n months to a YYYY-MM string."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    month += n
    while month > 12:
        month -= 12
        year += 1
    return f"{year:04d}-{month:02d}"


# ---------------------------------------------------------------------------
# Main Forecaster
# ---------------------------------------------------------------------------


class UsageForecaster:
    """
    Fits per-section, per-metric time-series models and generates
    month-ahead forecasts with 95 % prediction intervals.
    """

    # Exponential decay weight for trend fitting.
    # Keep this small: too large a decay confuses seasonal effects with trend.
    WEIGHT_DECAY = 0.05

    def __init__(self) -> None:
        self._models: Dict[Tuple[str, str], SectionModel] = {}
        self._is_fitted = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(self, monthly_df: pd.DataFrame) -> "UsageForecaster":
        """
        Train models from a monthly aggregated DataFrame.

        Uses a 2-pass iterative decomposition:
          1. Fit trend on log-space data (for log-space metrics).
          2. Compute seasonal indices from detrended series.
          3. Re-fit trend on seasonally-adjusted series for a cleaner slope.

        Parameters
        ----------
        monthly_df : pd.DataFrame
            Must contain columns:
            ``section_name``, ``year_month`` (YYYY-MM), and at minimum
            one of ``active_users``, ``cpu_usage_pct``, ``memory_usage_gb``,
            ``api_calls``.
        """
        monthly_df = monthly_df.sort_values(["section_name", "year_month"])
        for section in monthly_df["section_name"].unique():
            grp = monthly_df[monthly_df["section_name"] == section].reset_index(drop=True)
            for metric in _METRICS:
                if metric not in grp.columns:
                    continue
                y_raw = grp[metric].astype(float).values
                if len(y_raw) < 2:
                    continue

                use_log = metric in _LOG_SPACE_METRICS and (y_raw > 0).all()
                y = np.log(y_raw) if use_log else y_raw

                t = np.arange(1, len(y) + 1, dtype=float)
                months_arr = grp["year_month"].apply(lambda x: int(x[5:7])).values

                # --- Pass 1: initial trend with light recency weighting ---
                age = t.max() - t
                weights = np.exp(-self.WEIGHT_DECAY * age)
                ic1, sl1 = _weighted_linreg(t, y, weights)

                # Seasonal indices from detrended series
                trend1 = ic1 + sl1 * t
                if use_log:
                    detrended = y_raw / np.exp(trend1)
                else:
                    detrended = y_raw / np.where(trend1 != 0, trend1, 1.0)
                seasonal = _seasonal_indices(months_arr, detrended)

                # --- Pass 2: re-fit trend on seasonally-adjusted series ---
                si_arr = np.array([seasonal.get(m, 1.0) for m in months_arr])
                if use_log:
                    y_adj = np.log(y_raw / np.where(si_arr != 0, si_arr, 1.0))
                else:
                    y_adj = y_raw / np.where(si_arr != 0, si_arr, 1.0)
                intercept, slope = _weighted_linreg(t, y_adj, weights)

                # Residual std in original-space ratio for prediction intervals
                if use_log:
                    predicted_orig = np.exp(intercept + slope * t) * si_arr
                else:
                    predicted_orig = (intercept + slope * t) * si_arr
                ratio = y_raw / np.where(predicted_orig != 0, predicted_orig, 1.0)
                residual_std = float(np.std(ratio, ddof=1))

                self._models[(section, metric)] = SectionModel(
                    section_name=section,
                    metric_col=metric,
                    slope=slope,
                    intercept=intercept,
                    seasonal_indices=seasonal,
                    residual_std=residual_std,
                    n_obs=len(y_raw),
                    last_t=int(t.max()),
                    last_month=grp["year_month"].iloc[-1],
                    log_space=use_log,
                )

        self._is_fitted = True
        return self

    def predict(
        self,
        horizon: int = 3,
        confidence: float = 0.95,
    ) -> pd.DataFrame:
        """
        Generate forecasts for the next ``horizon`` months.

        Parameters
        ----------
        horizon : int
            Number of months ahead to forecast (default 3).
        confidence : float
            Confidence level for prediction intervals (default 0.95).

        Returns
        -------
        pd.DataFrame with columns:
            section_name, forecast_month, metric,
            predicted, ci_lower, ci_upper
        """
        if not self._is_fitted:
            raise RuntimeError("Call fit() before predict().")

        # z-score for two-sided confidence interval
        z = _z_score(confidence)
        records = []

        for (section, metric), model in self._models.items():
            for h in range(1, horizon + 1):
                future_t = model.last_t + h
                fcast_month = _add_months(model.last_month, h)
                month_num = int(fcast_month[5:7])
                si = model.seasonal_indices.get(month_num, 1.0)

                trend_val = model.intercept + model.slope * future_t

                if model.log_space:
                    # Back-transform from log-space, then apply seasonal index
                    predicted = max(0.0, math.exp(trend_val) * si)
                else:
                    predicted = max(0.0, trend_val * si)

                # 95 % prediction interval from residual spread (ratio-based)
                spread = predicted * model.residual_std * z
                ci_lower = max(0.0, predicted - spread)
                ci_upper = predicted + spread

                # Cap CPU at 100 %
                if metric == "cpu_usage_pct":
                    predicted = min(predicted, 100.0)
                    ci_lower = min(ci_lower, 100.0)
                    ci_upper = min(ci_upper, 100.0)

                records.append({
                    "section_name":   section,
                    "forecast_month": fcast_month,
                    "metric":         metric,
                    "predicted":      round(predicted, 4),
                    "ci_lower":       round(ci_lower, 4),
                    "ci_upper":       round(ci_upper, 4),
                })

        df = pd.DataFrame(records)
        return df.sort_values(["section_name", "forecast_month", "metric"]).reset_index(drop=True)

    def evaluate(self, actual_df: pd.DataFrame, forecast_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute per-section, per-metric accuracy scores.

        Parameters
        ----------
        actual_df : pd.DataFrame
            Columns: ``section_name``, ``year_month``, and metric columns.
        forecast_df : pd.DataFrame
            Output of ``predict()`` that covers the same year_months as actual_df.

        Returns
        -------
        pd.DataFrame with MAPE, accuracy_score (100 - MAPE) per section/metric.
        """
        records = []
        for metric in _METRICS:
            actuals = actual_df[["section_name", "year_month", metric]].rename(columns={metric: "actual"})
            preds = forecast_df[forecast_df["metric"] == metric][
                ["section_name", "forecast_month", "predicted"]
            ].rename(columns={"forecast_month": "year_month"})

            merged = actuals.merge(preds, on=["section_name", "year_month"], how="inner")
            if merged.empty:
                continue

            merged["ape"] = (
                (merged["predicted"] - merged["actual"]).abs()
                / merged["actual"].replace(0, np.nan)
                * 100
            )
            by_section = (
                merged.groupby("section_name")["ape"]
                .mean()
                .reset_index()
                .rename(columns={"ape": "mape"})
            )
            by_section["metric"] = metric
            by_section["accuracy_score"] = (100.0 - by_section["mape"]).clip(lower=0)
            records.append(by_section)

        if not records:
            return pd.DataFrame(columns=["section_name", "metric", "mape", "accuracy_score"])

        result = pd.concat(records, ignore_index=True)
        overall = (
            result.groupby("section_name")["accuracy_score"]
            .mean()
            .reset_index()
            .rename(columns={"accuracy_score": "overall_accuracy"})
        )
        return result.merge(overall, on="section_name").sort_values(
            ["section_name", "metric"]
        ).reset_index(drop=True)

    def scaling_recommendations(self, forecast_df: pd.DataFrame) -> pd.DataFrame:
        """
        Translate CPU and memory forecasts into plain-language scaling actions.

        Parameters
        ----------
        forecast_df : pd.DataFrame
            Output of ``predict()``.

        Returns
        -------
        pd.DataFrame with pm_summary column for product managers.
        """
        cpu = forecast_df[forecast_df["metric"] == "cpu_usage_pct"].copy()
        mem = forecast_df[forecast_df["metric"] == "memory_usage_gb"].copy()
        users = forecast_df[forecast_df["metric"] == "active_users"].copy()

        combined = (
            cpu[["section_name", "forecast_month", "predicted"]]
            .rename(columns={"predicted": "cpu_pct"})
            .merge(
                mem[["section_name", "forecast_month", "predicted"]].rename(
                    columns={"predicted": "memory_gb"}
                ),
                on=["section_name", "forecast_month"],
                how="outer",
            )
            .merge(
                users[["section_name", "forecast_month", "predicted"]].rename(
                    columns={"predicted": "active_users"}
                ),
                on=["section_name", "forecast_month"],
                how="outer",
            )
        )

        def _urgency(cpu: float) -> str:
            if cpu >= 85:
                return "critical"
            if cpu >= 70:
                return "high"
            if cpu >= 55:
                return "medium"
            return "low"

        def _action(cpu: float) -> str:
            if cpu >= 85:
                return "Immediate scale-up required – service degradation risk"
            if cpu >= 70:
                return "Plan capacity increase within the current sprint"
            if cpu >= 55:
                return "Monitor closely; proactively review capacity within 2 weeks"
            return "No scaling action needed; capacity is comfortable"

        def _pm_summary(row: pd.Series) -> str:
            return (
                f"In {row['forecast_month']}, the {row['section_name']} section is "
                f"forecast to have {int(row['active_users']):,} active users at "
                f"{row['cpu_pct']:.1f}% CPU load. "
                f"Recommendation: {_action(row['cpu_pct'])}."
            )

        combined["urgency"] = combined["cpu_pct"].apply(_urgency)
        combined["scaling_action"] = combined["cpu_pct"].apply(_action)
        combined["pm_summary"] = combined.apply(_pm_summary, axis=1)

        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        combined["_urgency_rank"] = combined["urgency"].map(urgency_order)
        return combined.sort_values(
            ["forecast_month", "_urgency_rank", "section_name"]
        ).drop(columns=["_urgency_rank"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _z_score(confidence: float) -> float:
    """Approximate z-score for a two-sided confidence interval."""
    # Use a lookup table for common values to avoid scipy dependency
    table = {
        0.80: 1.282,
        0.85: 1.440,
        0.90: 1.645,
        0.95: 1.960,
        0.99: 2.576,
    }
    if confidence in table:
        return table[confidence]
    # Rough approximation for other values
    p = (1.0 + confidence) / 2.0
    return float(math.sqrt(2) * _erfinv(2 * p - 1))


def _erfinv(x: float) -> float:
    """Approximate inverse error function (Winitzki 2008)."""
    a = 0.147
    ln = math.log(1 - x * x)
    part = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(math.sqrt(part * part - ln / a) - part), x)


# ---------------------------------------------------------------------------
# Convenience: load monthly aggregates from a daily CSV
# ---------------------------------------------------------------------------


def load_monthly_data(csv_path: str) -> pd.DataFrame:
    """
    Aggregate the daily platform_usage CSV into monthly averages/sums.

    Parameters
    ----------
    csv_path : str
        Path to the CSV produced by ``data/generate_data.py``.

    Returns
    -------
    pd.DataFrame with columns used by UsageForecaster.fit().
    """
    df = pd.read_csv(csv_path, parse_dates=["metric_date"])
    df["year_month"] = df["metric_date"].dt.strftime("%Y-%m")

    # We need a section_name column; use section_id if name not present
    if "section_name" not in df.columns:
        id_to_name = {
            1: "CI/CD",
            2: "Container Registry",
            3: "Git Storage",
            4: "Pages",
            5: "Runner Fleet",
            6: "Web IDE",
            7: "Monitoring",
            8: "API Gateway",
        }
        df["section_name"] = df["section_id"].map(id_to_name)

    monthly = (
        df.groupby(["section_name", "year_month"])
        .agg(
            active_users=("active_users", "mean"),
            api_calls=("api_calls", "sum"),
            cpu_usage_pct=("cpu_usage_pct", "mean"),
            memory_usage_gb=("memory_usage_gb", "mean"),
            storage_usage_gb=("storage_usage_gb", "mean"),
            pipeline_runs=("pipeline_runs", "sum"),
            error_rate_pct=("error_rate_pct", "mean"),
            avg_response_ms=("avg_response_ms", "mean"),
        )
        .reset_index()
        .sort_values(["section_name", "year_month"])
    )
    return monthly
