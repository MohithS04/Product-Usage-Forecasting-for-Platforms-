"""
report_generator.py
===================
Translates complex analytical forecast findings into simple, plain-English
reports for product managers.

Generates:
 - A markdown report (PM_Report_YYYY-MM.md)
 - A CSV export suitable for Tableau / Excel

Usage
-----
    python forecasting/report_generator.py \
        --data data/platform_usage.csv \
        --output reports/
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from typing import Optional

import pandas as pd

from forecasting.model import UsageForecaster, load_monthly_data
from forecasting.variance_analysis import run_variance_pipeline

# ---------------------------------------------------------------------------
# Narrative helpers
# ---------------------------------------------------------------------------

_URGENCY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}

_ACCURACY_BADGE = {
    True:  "✅ On Target (≥ 95%)",
    False: "⚠️  Below Target (< 95%)",
}


def _trend_word(current: float, previous: float, unit: str = "") -> str:
    """Return a human-readable trend phrase."""
    if previous == 0:
        return "—"
    pct = (current - previous) / previous * 100
    if pct > 10:
        return f"up {pct:.1f}%{unit} – significant growth"
    if pct > 3:
        return f"up {pct:.1f}%{unit}"
    if pct < -10:
        return f"down {pct:.1f}%{unit} – notable decline"
    if pct < -3:
        return f"down {pct:.1f}%{unit}"
    return "roughly steady"


def _urgency_from_cpu(cpu: float) -> str:
    if cpu >= 85:
        return "critical"
    if cpu >= 70:
        return "high"
    if cpu >= 55:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_pm_report(
    monthly_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    variance_df: Optional[pd.DataFrame],
    report_month: str,
) -> str:
    """
    Build a markdown product-manager report.

    Parameters
    ----------
    monthly_df   : Monthly actuals (output of load_monthly_data).
    forecast_df  : Forecast output from UsageForecaster.predict().
    variance_df  : Variance output from compute_variance(), or None.
    report_month : YYYY-MM string for the report header.

    Returns
    -------
    Markdown string.
    """
    lines = []
    lines += [
        f"# GitLab Platform Usage Forecast — {report_month}",
        "",
        "> **Audience**: Product Managers  ",
        "> **Purpose**: Summarise platform load trends and infrastructure "
        "scaling needs for the next 3 months  ",
        "> **Generated**: " + date.today().isoformat(),
        "",
        "---",
        "",
    ]

    # ── Executive Summary ──────────────────────────────────────────────────
    lines += ["## Executive Summary", ""]

    # Latest actual month
    latest_month = monthly_df["year_month"].max()
    prev_month   = sorted(monthly_df["year_month"].unique())[-2] \
                   if len(monthly_df["year_month"].unique()) >= 2 else None

    latest = monthly_df[monthly_df["year_month"] == latest_month]
    total_users = int(latest["active_users"].sum())
    total_api   = int(latest["api_calls"].sum())
    avg_cpu     = float(latest["cpu_usage_pct"].mean())

    lines.append(
        f"In **{latest_month}**, the GitLab platform served a combined "
        f"**{total_users:,} active users** across all sections, "
        f"handling **{total_api:,} API calls** at an average CPU load of "
        f"**{avg_cpu:.1f}%**."
    )
    lines.append("")

    if prev_month:
        prev = monthly_df[monthly_df["year_month"] == prev_month]
        prev_users = int(prev["active_users"].sum())
        trend = _trend_word(total_users, prev_users)
        lines.append(
            f"User activity is **{trend}** compared to {prev_month}."
        )
        lines.append("")

    # Overall accuracy
    if variance_df is not None and not variance_df.empty:
        overall_acc = float(variance_df["accuracy_score"].mean())
        lines += [
            f"The forecasting model achieved an overall accuracy of "
            f"**{overall_acc:.1f}%** — "
            + ("above" if overall_acc >= 95 else "approaching")
            + " the **95% project target**.",
            "",
        ]

    lines += ["---", ""]

    # ── Section-by-Section Forecast ────────────────────────────────────────
    lines += ["## Platform Section Forecasts (Next 3 Months)", ""]

    sections = sorted(forecast_df["section_name"].unique())
    for section in sections:
        sec_fc = forecast_df[forecast_df["section_name"] == section]
        sec_actual = monthly_df[monthly_df["section_name"] == section]
        last_actual = sec_actual.sort_values("year_month").iloc[-1] \
                      if not sec_actual.empty else None

        lines.append(f"### {section}")
        lines.append("")

        # Forecast table
        cpu_rows = sec_fc[sec_fc["metric"] == "cpu_usage_pct"].sort_values("forecast_month")
        user_rows = sec_fc[sec_fc["metric"] == "active_users"].sort_values("forecast_month")
        mem_rows  = sec_fc[sec_fc["metric"] == "memory_usage_gb"].sort_values("forecast_month")

        lines.append(
            "| Month | Users (forecast) | CPU % | Memory (GB) | Scaling Action |"
        )
        lines.append(
            "|-------|-----------------|-------|-------------|----------------|"
        )

        for _, cpu_row in cpu_rows.iterrows():
            fm = cpu_row["forecast_month"]
            cpu_val = cpu_row["predicted"]
            urgency = _urgency_from_cpu(cpu_val)
            emoji = _URGENCY_EMOJI[urgency]

            user_val = user_rows[user_rows["forecast_month"] == fm]["predicted"].values
            mem_val  = mem_rows[mem_rows["forecast_month"] == fm]["predicted"].values

            user_str = f"{int(user_val[0]):,}" if len(user_val) else "—"
            mem_str  = f"{mem_val[0]:.1f}" if len(mem_val) else "—"

            if urgency in ("critical", "high"):
                action = f"{emoji} **Scale up capacity**"
            elif urgency == "medium":
                action = f"{emoji} Monitor closely"
            else:
                action = f"{emoji} No action needed"

            lines.append(f"| {fm} | {user_str} | {cpu_val:.1f}% | {mem_str} | {action} |")

        lines.append("")

        # Plain-language insight
        if last_actual is not None and not cpu_rows.empty:
            next_cpu = float(cpu_rows.iloc[0]["predicted"])
            curr_cpu = float(last_actual["cpu_usage_pct"])
            trend_cpu = _trend_word(next_cpu, curr_cpu, "%")
            next_users = user_rows.iloc[0]["predicted"] if not user_rows.empty else None
            curr_users = float(last_actual["active_users"])

            insight = (
                f"**Key insight**: CPU load for {section} is forecast to be "
                f"**{trend_cpu}** next month ({next_cpu:.1f}% vs {curr_cpu:.1f}% currently)."
            )
            if next_users:
                user_trend = _trend_word(float(next_users), curr_users)
                insight += (
                    f" User activity is expected to be **{user_trend}**."
                )
            lines += [insight, ""]

    lines += ["---", ""]

    # ── Variance Analysis ──────────────────────────────────────────────────
    if variance_df is not None and not variance_df.empty:
        lines += ["## Forecast Accuracy — Last 3 Months", ""]
        lines.append(
            "This section shows how well our forecasts matched reality, "
            "helping us build confidence in future projections."
        )
        lines.append("")

        acc_by_section = (
            variance_df.groupby("section_name")["accuracy_score"]
            .mean()
            .reset_index()
            .sort_values("accuracy_score", ascending=False)
        )
        lines.append("| Section | Avg Accuracy | Status |")
        lines.append("|---------|--------------|--------|")
        for _, row in acc_by_section.iterrows():
            badge = _ACCURACY_BADGE[row["accuracy_score"] >= 95]
            lines.append(
                f"| {row['section_name']} | {row['accuracy_score']:.1f}% | {badge} |"
            )
        lines.append("")
        lines += ["---", ""]

    # ── Infrastructure Scaling Summary ─────────────────────────────────────
    lines += ["## Infrastructure Scaling Summary", ""]
    lines.append(
        "The table below highlights sections that need capacity attention "
        "in the coming months. Sections are sorted from most urgent to least."
    )
    lines.append("")

    recs = UsageForecaster().fit(monthly_df).scaling_recommendations(forecast_df)
    urgent = recs[recs["urgency"].isin(["critical", "high", "medium"])]

    if urgent.empty:
        lines.append(
            "✅ **No scaling actions required.** All sections are forecast "
            "to remain within comfortable capacity bounds."
        )
    else:
        lines.append("| Priority | Section | Month | CPU Forecast | Action |")
        lines.append("|----------|---------|-------|--------------|--------|")
        for _, row in urgent.iterrows():
            emoji = _URGENCY_EMOJI[row["urgency"]]
            lines.append(
                f"| {emoji} {row['urgency'].capitalize()} "
                f"| {row['section_name']} "
                f"| {row['forecast_month']} "
                f"| {row['cpu_pct']:.1f}% "
                f"| {row['scaling_action']} |"
            )

    lines += ["", "---", ""]

    # ── Glossary ───────────────────────────────────────────────────────────
    lines += [
        "## Glossary",
        "",
        "| Term | Meaning |",
        "|------|---------|",
        "| **Active Users** | Distinct users who performed at least one action in the period |",
        "| **CPU %** | Average percentage of CPU capacity consumed across all nodes |",
        "| **Memory (GB)** | Average RAM consumed in gigabytes |",
        "| **API Calls** | Total API requests received by the platform section |",
        "| **Accuracy Score** | 100 minus the Mean Absolute Percentage Error (MAPE); "
        "higher is better |",
        "| **Scaling Action** | Infrastructure change recommended based on forecast |",
        "",
        "---",
        "",
        "*Report generated automatically by the Product Usage Forecasting pipeline.*",
        "*For questions, contact the Platform Analytics team.*",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tableau-ready CSV export
# ---------------------------------------------------------------------------


def export_tableau_csv(
    monthly_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    variance_df: Optional[pd.DataFrame],
    output_dir: str,
) -> None:
    """
    Write Tableau-ready CSV files: actuals, forecasts, and variance.
    """
    # Tableau CSVs
    os.makedirs(output_dir, exist_ok=True)
    export_date = date.today().strftime("%Y-%m-%d")

    # Actuals (wide format)
    actuals_path = os.path.join(output_dir, f"actuals_{export_date}.csv")
    monthly_df.to_csv(actuals_path, index=False)
    print(f"[OK] Actuals CSV  → {actuals_path}")

    # Forecasts (long format, already suitable for Tableau)
    forecasts_path = os.path.join(output_dir, f"forecasts_{export_date}.csv")
    forecast_df.to_csv(forecasts_path, index=False)
    print(f"[OK] Forecasts CSV → {forecasts_path}")

    # Variance
    if variance_df is not None and not variance_df.empty:
        variance_path = os.path.join(output_dir, f"variance_{export_date}.csv")
        variance_df.to_csv(variance_path, index=False)
        print(f"[OK] Variance CSV  → {variance_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate PM-friendly forecast reports and Tableau exports."
    )
    parser.add_argument(
        "--data",
        default=os.path.join(os.path.dirname(__file__), "..", "data", "platform_usage.csv"),
        help="Path to daily platform usage CSV",
    )
    parser.add_argument(
        "--output",
        default="reports",
        help="Output directory (default: reports/)",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=3,
        help="Forecast horizon in months (default: 3)",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.data):
        print(f"[ERROR] Data file not found: {args.data}")
        print("  Run:  python data/generate_data.py")
        return 1

    os.makedirs(args.output, exist_ok=True)
    report_month = date.today().strftime("%Y-%m")

    # Load data
    print("Loading monthly data …")
    monthly = load_monthly_data(args.data)

    # Fit + forecast
    print("Fitting forecasting model …")
    forecaster = UsageForecaster()
    forecaster.fit(monthly)
    forecast_df = forecaster.predict(horizon=args.horizon)

    # Variance (use last 3 months as holdout)
    variance_df = None
    all_months = sorted(monthly["year_month"].unique())
    if len(all_months) > 3:
        from forecasting.variance_analysis import compute_variance
        train_months = all_months[:-3]
        test_months  = all_months[-3:]
        train_df = monthly[monthly["year_month"].isin(train_months)]
        test_df  = monthly[monthly["year_month"].isin(test_months)]
        forecaster2 = UsageForecaster()
        forecaster2.fit(train_df)
        holdout_fc = forecaster2.predict(horizon=3)
        variance_df = compute_variance(test_df, holdout_fc)

    # Build markdown report
    print("Generating PM report …")
    report_md = build_pm_report(monthly, forecast_df, variance_df, report_month)

    md_path = os.path.join(args.output, f"PM_Report_{report_month}.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(report_md)
    print(f"[OK] PM Report     → {md_path}")

    # Tableau CSVs
    export_tableau_csv(monthly, forecast_df, variance_df, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
