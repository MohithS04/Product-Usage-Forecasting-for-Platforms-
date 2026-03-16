"""
variance_analysis.py
====================
Automated monthly performance variance analysis.

Compares forecast values against actuals to:
 - Compute MAPE and accuracy score per section and metric
 - Flag sections falling below 95 % accuracy
 - Generate a structured variance report (CSV + console summary)
 - Eliminate manual reconciliation for recurring reporting cycles

Usage
-----
    python forecasting/variance_analysis.py \
        --data data/platform_usage.csv \
        --output reports/variance_YYYY-MM.csv
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from forecasting.model import UsageForecaster, load_monthly_data

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_ACCURACY = 95.0          # project target: ≥ 95 % accuracy
METRICS = ["active_users", "cpu_usage_pct", "memory_usage_gb", "api_calls"]


# ---------------------------------------------------------------------------
# Core variance computation
# ---------------------------------------------------------------------------


def compute_variance(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute month-level variance between actuals and forecasts.

    Parameters
    ----------
    actuals : pd.DataFrame
        Monthly actual data with columns: section_name, year_month, <metrics>.
    forecasts : pd.DataFrame
        Forecast output (long format) with columns:
        section_name, forecast_month, metric, predicted.

    Returns
    -------
    pd.DataFrame with columns:
        section_name, year_month, metric,
        actual, predicted, variance_abs, variance_pct,
        within_target (bool)
    """
    records = []
    forecasts_wide = forecasts.pivot_table(
        index=["section_name", "forecast_month"],
        columns="metric",
        values="predicted",
    ).reset_index().rename(columns={"forecast_month": "year_month"})

    merged = actuals.merge(forecasts_wide, on=["section_name", "year_month"], how="inner")

    for metric in METRICS:
        actual_col = metric
        pred_col = metric + "_y" if metric + "_y" in merged.columns else metric
        # Handle pivot suffix collision
        if metric + "_y" in merged.columns:
            actual_col = metric + "_x"

        if actual_col not in merged.columns or pred_col not in merged.columns:
            continue

        sub = merged[["section_name", "year_month", actual_col, pred_col]].copy()
        sub = sub.rename(columns={actual_col: "actual", pred_col: "predicted"})
        sub["metric"] = metric
        sub["variance_abs"] = sub["predicted"] - sub["actual"]
        sub["variance_pct"] = (
            (sub["predicted"] - sub["actual"]) / sub["actual"].replace(0, np.nan) * 100
        ).round(4)
        sub["ape"] = sub["variance_pct"].abs()
        sub["accuracy_score"] = (100.0 - sub["ape"]).clip(lower=0)
        sub["within_target"] = sub["accuracy_score"] >= TARGET_ACCURACY
        records.append(sub[["section_name", "year_month", "metric",
                             "actual", "predicted", "variance_abs",
                             "variance_pct", "accuracy_score", "within_target"]])

    if not records:
        return pd.DataFrame()

    return pd.concat(records, ignore_index=True).sort_values(
        ["section_name", "year_month", "metric"]
    )


def monthly_summary(variance_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-metric variance rows into an overall monthly accuracy score
    per section.
    """
    summary = (
        variance_df.groupby(["section_name", "year_month"])
        .agg(
            avg_accuracy=("accuracy_score", "mean"),
            min_accuracy=("accuracy_score", "min"),
            max_accuracy=("accuracy_score", "max"),
            pct_metrics_on_target=("within_target", "mean"),
        )
        .reset_index()
    )
    summary["avg_accuracy"] = summary["avg_accuracy"].round(2)
    summary["min_accuracy"] = summary["min_accuracy"].round(2)
    summary["max_accuracy"] = summary["max_accuracy"].round(2)
    summary["pct_metrics_on_target"] = (summary["pct_metrics_on_target"] * 100).round(1)
    summary["meets_95_pct_target"] = summary["avg_accuracy"] >= TARGET_ACCURACY
    return summary.sort_values(["year_month", "avg_accuracy"], ascending=[True, False])


# ---------------------------------------------------------------------------
# Run a full train-test variance analysis on the available history
# ---------------------------------------------------------------------------


def run_variance_pipeline(
    csv_path: str,
    holdout_months: int = 3,
    output_dir: str = "reports",
) -> pd.DataFrame:
    """
    End-to-end variance pipeline:
    1. Load monthly data from CSV.
    2. Split into train / holdout.
    3. Fit forecaster on training data.
    4. Predict on holdout months.
    5. Compute variance vs actuals.
    6. Print summary and save CSV.

    Parameters
    ----------
    csv_path : str
        Path to the daily usage CSV.
    holdout_months : int
        Number of trailing months to use as held-out actuals (default 3).
    output_dir : str
        Directory to write variance CSV reports.

    Returns
    -------
    pd.DataFrame with variance results.
    """
    print(f"\n{'='*60}")
    print("  Monthly Performance Variance Analysis")
    print(f"{'='*60}")

    monthly = load_monthly_data(csv_path)

    # Chronological split
    all_months = sorted(monthly["year_month"].unique())
    if len(all_months) <= holdout_months:
        raise ValueError(
            f"Need more than {holdout_months} months of data; got {len(all_months)}."
        )

    train_months = all_months[:-holdout_months]
    test_months  = all_months[-holdout_months:]

    train_df = monthly[monthly["year_month"].isin(train_months)]
    test_df  = monthly[monthly["year_month"].isin(test_months)]

    print(f"\nTraining period : {train_months[0]}  →  {train_months[-1]} ({len(train_months)} months)")
    print(f"Evaluation period: {test_months[0]}  →  {test_months[-1]} ({len(test_months)} months)")
    print(f"Sections: {sorted(monthly['section_name'].unique())}")

    # Fit and forecast
    forecaster = UsageForecaster()
    forecaster.fit(train_df)
    forecast_df = forecaster.predict(horizon=holdout_months)

    # Compute variance
    variance_df = compute_variance(test_df, forecast_df)
    if variance_df.empty:
        print("\n[WARN] No overlapping months found between forecasts and actuals.")
        return pd.DataFrame()

    summary = monthly_summary(variance_df)

    # Console report
    _print_summary(summary, variance_df)

    # Save reports
    os.makedirs(output_dir, exist_ok=True)
    report_month = date.today().strftime("%Y-%m")
    variance_path = os.path.join(output_dir, f"variance_{report_month}.csv")
    summary_path  = os.path.join(output_dir, f"variance_summary_{report_month}.csv")
    variance_df.to_csv(variance_path, index=False)
    summary.to_csv(summary_path, index=False)
    print(f"\n[OK] Detailed variance saved to: {variance_path}")
    print(f"[OK] Summary saved to: {summary_path}")

    return variance_df


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------


def _print_summary(summary: pd.DataFrame, variance_df: pd.DataFrame) -> None:
    print(f"\n{'─'*60}")
    print("  Overall Accuracy by Section (averaged across metrics)")
    print(f"{'─'*60}")

    section_acc = (
        variance_df.groupby("section_name")["accuracy_score"]
        .mean()
        .reset_index()
        .rename(columns={"accuracy_score": "overall_accuracy"})
        .sort_values("overall_accuracy", ascending=False)
    )
    section_acc["overall_accuracy"] = section_acc["overall_accuracy"].round(2)
    section_acc["status"] = section_acc["overall_accuracy"].apply(
        lambda x: "✅ Meets target" if x >= TARGET_ACCURACY else "⚠️  Below target"
    )

    col_w = max(len(s) for s in section_acc["section_name"]) + 2
    print(f"  {'Section':<{col_w}} {'Accuracy':>10}  Status")
    print(f"  {'─'*col_w} {'─'*10}  {'─'*20}")
    for _, row in section_acc.iterrows():
        print(f"  {row['section_name']:<{col_w}} {row['overall_accuracy']:>9.2f}%  {row['status']}")

    global_acc = section_acc["overall_accuracy"].mean()
    print(f"\n  {'Global average':<{col_w}} {global_acc:>9.2f}%")
    print(f"  Project target                     {TARGET_ACCURACY:.1f}%")
    target_met = global_acc >= TARGET_ACCURACY
    banner = "✅ TARGET MET" if target_met else "⚠️  TARGET NOT YET MET"
    print(f"\n  {banner}")

    # Worst misses
    worst = variance_df.nsmallest(5, "accuracy_score")[
        ["section_name", "year_month", "metric", "actual", "predicted", "accuracy_score"]
    ]
    if not worst.empty:
        print(f"\n{'─'*60}")
        print("  Top 5 Largest Forecast Misses")
        print(f"{'─'*60}")
        print(worst.to_string(index=False))

    print(f"\n{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Automated monthly forecast variance analysis."
    )
    parser.add_argument(
        "--data",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "platform_usage.csv"),
        help="Path to daily platform usage CSV (default: data/platform_usage.csv)",
    )
    parser.add_argument(
        "--holdout",
        type=int,
        default=3,
        help="Number of trailing months used as held-out actuals (default: 3)",
    )
    parser.add_argument(
        "--output",
        default="reports",
        help="Output directory for variance CSV reports (default: reports/)",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.data):
        print(f"[ERROR] Data file not found: {args.data}")
        print("  Run:  python data/generate_data.py  to create sample data.")
        return 1

    run_variance_pipeline(
        csv_path=args.data,
        holdout_months=args.holdout,
        output_dir=args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
