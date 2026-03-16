"""Report generator that translates complex analytical findings into simple
language for product managers to support evidence-based roadmapping.
"""

import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import DEFAULT_SECTIONS


def _section_name(section_id: int) -> str:
    """Look up a human-readable section name."""
    for s in DEFAULT_SECTIONS:
        if s["section_id"] == section_id:
            return s["section_name"]
    return f"Section {section_id}"


def _format_number(value: float) -> str:
    """Format a number into a human-readable string."""
    abs_val = abs(value)
    if abs_val >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_val >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.1f}"


def generate_executive_summary(
    forecasts_df: pd.DataFrame,
    variance_summary: dict,
) -> str:
    """Create a plain-language executive summary.

    Parameters
    ----------
    forecasts_df : pd.DataFrame
        Forecast results from ``generate_all_forecasts``.
    variance_summary : dict
        Output of ``summarize_variance_report``.

    Returns
    -------
    str
        A multi-paragraph summary suitable for product managers.
    """
    lines = [
        "=" * 60,
        "PRODUCT USAGE FORECAST – EXECUTIVE SUMMARY",
        f"Report Date: {date.today().isoformat()}",
        "=" * 60,
        "",
    ]

    # Variance overview
    total = variance_summary.get("total_metrics", 0)
    on_track = variance_summary.get("on_track_count", 0)
    avg_var = variance_summary.get("avg_absolute_variance", 0.0)
    accuracy = max(0.0, 100.0 - avg_var)

    lines.append("FORECAST ACCURACY")
    lines.append("-" * 40)
    if total > 0:
        lines.append(
            f"  {on_track} of {total} metrics are on track "
            f"(within 5% of forecast)."
        )
        lines.append(f"  Average absolute variance: {avg_var:.1f}%")
        lines.append(f"  Overall forecast accuracy: {accuracy:.1f}%")
    else:
        lines.append("  No variance data available yet.")
    lines.append("")

    # Growth highlights per section
    if not forecasts_df.empty:
        lines.append("GROWTH HIGHLIGHTS (next 6 months)")
        lines.append("-" * 40)

        for sid in sorted(forecasts_df["section_id"].unique()):
            sec_data = forecasts_df[forecasts_df["section_id"] == sid]
            name = _section_name(int(sid))
            first_month = sec_data.groupby("metric_name")["predicted_value"].first()
            last_month = sec_data.groupby("metric_name")["predicted_value"].last()
            growth = ((last_month - first_month) / first_month * 100).mean()
            lines.append(
                f"  {name}: projected {growth:.1f}% average growth across metrics"
            )
        lines.append("")

    # Scaling recommendations
    lines.append("SCALING RECOMMENDATIONS")
    lines.append("-" * 40)
    if not forecasts_df.empty:
        for sid in sorted(forecasts_df["section_id"].unique()):
            sec_forecasts = forecasts_df[forecasts_df["section_id"] == sid]
            max_compute = sec_forecasts.loc[
                sec_forecasts["metric_name"] == "compute_hours", "upper_bound"
            ]
            if not max_compute.empty and max_compute.max() > 10000:
                lines.append(
                    f"  ⚠ {_section_name(int(sid))}: compute capacity scale-up recommended "
                    f"(peak forecast: {_format_number(max_compute.max())} hours)"
                )

            max_storage = sec_forecasts.loc[
                sec_forecasts["metric_name"] == "storage_gb", "upper_bound"
            ]
            if not max_storage.empty and max_storage.max() > 5000:
                lines.append(
                    f"  ⚠ {_section_name(int(sid))}: storage expansion needed "
                    f"(peak forecast: {_format_number(max_storage.max())} GB)"
                )
    else:
        lines.append("  No forecast data available.")
    lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def generate_section_detail(
    section_id: int,
    forecasts_df: pd.DataFrame,
    variance_df: pd.DataFrame,
) -> str:
    """Generate a detailed, plain-language report for a single section.

    Parameters
    ----------
    section_id : int
        The platform section to report on.
    forecasts_df : pd.DataFrame
        All forecasts (will be filtered to section_id).
    variance_df : pd.DataFrame
        Variance report (will be filtered to section_id).

    Returns
    -------
    str
        A plain-language section report.
    """
    name = _section_name(section_id)
    lines = [
        f"Section Detail: {name}",
        "-" * 40,
    ]

    sec_forecasts = forecasts_df[forecasts_df["section_id"] == section_id]
    sec_variance = variance_df[variance_df["section_id"] == section_id] if not variance_df.empty else pd.DataFrame()

    if sec_forecasts.empty:
        lines.append("  No forecast data available for this section.")
        return "\n".join(lines)

    for metric in sec_forecasts["metric_name"].unique():
        m_data = sec_forecasts[sec_forecasts["metric_name"] == metric]
        first_val = m_data["predicted_value"].iloc[0]
        last_val = m_data["predicted_value"].iloc[-1]
        change = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0

        direction = "increase" if change >= 0 else "decrease"
        lines.append(
            f"  {metric}: Expected to {direction} by {abs(change):.1f}% "
            f"(from {_format_number(first_val)} to {_format_number(last_val)})"
        )

        if not sec_variance.empty:
            v_row = sec_variance[sec_variance["metric_name"] == metric]
            if not v_row.empty:
                status = v_row.iloc[0]["status"]
                var_pct = v_row.iloc[0]["variance_pct"]
                lines.append(
                    f"    Last month: {status} (variance: {var_pct:+.1f}%)"
                )

    lines.append("")
    return "\n".join(lines)
