"""Automated monthly performance variance analysis.

Compares actual usage against forecasted values and categorises deviations
to eliminate manual reconciliation for recurring reporting cycles.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import METRIC_COLUMNS, VARIANCE_THRESHOLDS


def compute_variance(actual: float, forecast: float) -> float:
    """Return the percentage variance of actual vs forecast.

    A positive value means actual exceeded the forecast.
    """
    if forecast == 0:
        return 0.0
    return round(((actual - forecast) / forecast) * 100, 2)


def classify_variance(variance_pct: float) -> str:
    """Classify a variance percentage into a human-readable status."""
    abs_var = abs(variance_pct)
    if abs_var <= VARIANCE_THRESHOLDS["on_track"]:
        return "On Track"
    if abs_var <= VARIANCE_THRESHOLDS["minor_deviation"]:
        return "Minor Deviation"
    if abs_var <= VARIANCE_THRESHOLDS["significant_deviation"]:
        return "Significant Deviation"
    return "Critical Deviation"


def run_variance_analysis(
    actuals_df: pd.DataFrame,
    forecasts_df: pd.DataFrame,
) -> pd.DataFrame:
    """Run automated variance analysis for each section and metric.

    Parameters
    ----------
    actuals_df : pd.DataFrame
        Must contain ``section_id``, ``report_month``, and metric columns.
    forecasts_df : pd.DataFrame
        Must contain ``section_id``, ``metric_name``, and ``predicted_value``
        with a ``forecast_date`` that aligns to the report month.

    Returns
    -------
    pd.DataFrame
        Variance report with columns: section_id, report_month, metric_name,
        actual_value, forecast_value, variance_pct, status, direction.
    """
    actuals_df = actuals_df.copy()
    forecasts_df = forecasts_df.copy()

    # Normalize date columns
    actuals_df["report_month"] = pd.to_datetime(actuals_df["report_month"]).dt.to_period("M")
    forecasts_df["forecast_date"] = pd.to_datetime(forecasts_df["forecast_date"]).dt.to_period("M")

    results = []
    for _, actual_row in actuals_df.iterrows():
        sid = actual_row["section_id"]
        month = actual_row["report_month"]

        for metric in METRIC_COLUMNS:
            if metric not in actual_row.index:
                continue
            actual_val = float(actual_row[metric])

            # Find matching forecast
            mask = (
                (forecasts_df["section_id"] == sid)
                & (forecasts_df["metric_name"] == metric)
                & (forecasts_df["forecast_date"] == month)
            )
            matched = forecasts_df.loc[mask]
            if matched.empty:
                continue

            forecast_val = float(matched.iloc[0]["predicted_value"])
            var_pct = compute_variance(actual_val, forecast_val)

            results.append({
                "section_id": sid,
                "report_month": str(month),
                "metric_name": metric,
                "actual_value": actual_val,
                "forecast_value": forecast_val,
                "variance_pct": var_pct,
                "status": classify_variance(var_pct),
                "direction": "Over Forecast" if var_pct > 0 else "Under Forecast",
            })

    return pd.DataFrame(results)


def summarize_variance_report(report_df: pd.DataFrame) -> dict:
    """Produce a summary of the variance report.

    Returns
    -------
    dict
        Keys: total_metrics, on_track_count, deviation_count,
        avg_absolute_variance, worst_metric.
    """
    if report_df.empty:
        return {
            "total_metrics": 0,
            "on_track_count": 0,
            "deviation_count": 0,
            "avg_absolute_variance": 0.0,
            "worst_metric": None,
        }

    on_track = int((report_df["status"] == "On Track").sum())
    total = len(report_df)
    avg_abs = round(float(report_df["variance_pct"].abs().mean()), 2)
    worst_idx = report_df["variance_pct"].abs().idxmax()
    worst = report_df.loc[worst_idx]

    return {
        "total_metrics": total,
        "on_track_count": on_track,
        "deviation_count": total - on_track,
        "avg_absolute_variance": avg_abs,
        "worst_metric": {
            "section_id": int(worst["section_id"]),
            "metric_name": worst["metric_name"],
            "variance_pct": float(worst["variance_pct"]),
        },
    }
