"""
generate_data.py
================
Generates realistic synthetic historical platform usage data for 24 months
across all GitLab platform sections. Outputs a CSV that can be loaded into
the database via ``data_ingestion.sql`` or used directly by the forecasting
model.

Usage
-----
    python data/generate_data.py
    python data/generate_data.py --months 36 --output data/platform_usage.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
from datetime import date, timedelta
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Section definitions – baseline usage profiles
# ---------------------------------------------------------------------------

SECTIONS: List[Dict] = [
    {
        "section_id": 1,
        "section_name": "CI/CD",
        "base_users": 12_000,
        "base_cpu": 58.0,
        "base_memory_gb": 210.0,
        "base_storage_gb": 3_200.0,
        "base_api_calls": 4_500_000,
        "base_pipelines": 85_000,
        "growth_rate": 0.025,        # 2.5% monthly user growth
        "cpu_per_user_factor": 0.003,
        "seasonal_amplitude": 0.12,
        "peak_month": 3,             # March = highest usage month
    },
    {
        "section_id": 2,
        "section_name": "Container Registry",
        "base_users": 8_500,
        "base_cpu": 45.0,
        "base_memory_gb": 160.0,
        "base_storage_gb": 18_000.0,
        "base_api_calls": 2_200_000,
        "base_pipelines": 0,
        "growth_rate": 0.030,
        "cpu_per_user_factor": 0.002,
        "seasonal_amplitude": 0.08,
        "peak_month": 4,
    },
    {
        "section_id": 3,
        "section_name": "Git Storage",
        "base_users": 22_000,
        "base_cpu": 62.0,
        "base_memory_gb": 280.0,
        "base_storage_gb": 55_000.0,
        "base_api_calls": 9_800_000,
        "base_pipelines": 0,
        "growth_rate": 0.018,
        "cpu_per_user_factor": 0.002,
        "seasonal_amplitude": 0.10,
        "peak_month": 2,
    },
    {
        "section_id": 4,
        "section_name": "Pages",
        "base_users": 3_200,
        "base_cpu": 28.0,
        "base_memory_gb": 80.0,
        "base_storage_gb": 6_500.0,
        "base_api_calls": 750_000,
        "base_pipelines": 12_000,
        "growth_rate": 0.020,
        "cpu_per_user_factor": 0.004,
        "seasonal_amplitude": 0.15,
        "peak_month": 6,
    },
    {
        "section_id": 5,
        "section_name": "Runner Fleet",
        "base_users": 15_000,
        "base_cpu": 72.0,
        "base_memory_gb": 320.0,
        "base_storage_gb": 9_800.0,
        "base_api_calls": 6_100_000,
        "base_pipelines": 210_000,
        "growth_rate": 0.028,
        "cpu_per_user_factor": 0.003,
        "seasonal_amplitude": 0.18,
        "peak_month": 3,
    },
    {
        "section_id": 6,
        "section_name": "Web IDE",
        "base_users": 5_500,
        "base_cpu": 38.0,
        "base_memory_gb": 120.0,
        "base_storage_gb": 2_100.0,
        "base_api_calls": 1_400_000,
        "base_pipelines": 0,
        "growth_rate": 0.035,
        "cpu_per_user_factor": 0.005,
        "seasonal_amplitude": 0.09,
        "peak_month": 10,
    },
    {
        "section_id": 7,
        "section_name": "Monitoring",
        "base_users": 2_800,
        "base_cpu": 42.0,
        "base_memory_gb": 90.0,
        "base_storage_gb": 4_400.0,
        "base_api_calls": 980_000,
        "base_pipelines": 0,
        "growth_rate": 0.015,
        "cpu_per_user_factor": 0.006,
        "seasonal_amplitude": 0.06,
        "peak_month": 1,
    },
    {
        "section_id": 8,
        "section_name": "API Gateway",
        "base_users": 18_000,
        "base_cpu": 55.0,
        "base_memory_gb": 190.0,
        "base_storage_gb": 1_200.0,
        "base_api_calls": 14_000_000,
        "base_pipelines": 0,
        "growth_rate": 0.022,
        "cpu_per_user_factor": 0.001,
        "seasonal_amplitude": 0.07,
        "peak_month": 11,
    },
]


def _seasonal_factor(month: int, peak_month: int, amplitude: float) -> float:
    """Return a multiplicative seasonal factor in [1-amp, 1+amp]."""
    phase = 2 * math.pi * (month - peak_month) / 12
    return 1.0 + amplitude * math.cos(phase)


def _day_of_week_factor(d: date) -> float:
    """Business days have higher usage; weekends ~40% lower."""
    return 1.0 if d.weekday() < 5 else 0.60


def generate_daily_rows(
    section: Dict,
    start_date: date,
    end_date: date,
    rng: random.Random,
) -> List[Tuple]:
    """Generate one row per calendar day for a single section."""
    rows: List[Tuple] = []
    total_days = (end_date - start_date).days
    sid = section["section_id"]

    current = start_date
    day_idx = 0
    while current <= end_date:
        month_idx = (current.year - start_date.year) * 12 + (current.month - start_date.month)
        growth = (1 + section["growth_rate"]) ** month_idx
        seasonal = _seasonal_factor(current.month, section["peak_month"], section["seasonal_amplitude"])
        dow = _day_of_week_factor(current)

        noise_u = rng.gauss(1.0, 0.04)
        noise_c = rng.gauss(1.0, 0.035)
        noise_m = rng.gauss(1.0, 0.030)
        noise_s = rng.gauss(1.0, 0.020)
        noise_a = rng.gauss(1.0, 0.045)
        noise_p = rng.gauss(1.0, 0.06)

        active_users = max(1, int(section["base_users"] * growth * seasonal * dow * noise_u))
        cpu_pct = min(99.9, max(0.1, section["base_cpu"] * growth * seasonal * dow * noise_c))
        memory_gb = max(0.1, section["base_memory_gb"] * growth * seasonal * noise_m)
        storage_gb = max(0.1, section["base_storage_gb"] * (1 + 0.005 * day_idx) * noise_s)
        api_calls = max(0, int(section["base_api_calls"] * growth * seasonal * dow * noise_a))
        pipelines = max(0, int(section["base_pipelines"] * growth * seasonal * dow * noise_p))

        error_rate = max(0.0, min(20.0, rng.gauss(0.8, 0.3) if cpu_pct < 80 else rng.gauss(2.5, 0.8)))
        response_ms = max(10.0, rng.gauss(120.0 + cpu_pct * 1.5, 15.0))

        rows.append((
            sid,
            current.isoformat(),
            active_users,
            api_calls,
            round(cpu_pct, 2),
            round(memory_gb, 2),
            round(storage_gb, 2),
            pipelines,
            round(error_rate, 2),
            round(response_ms, 2),
        ))

        current += timedelta(days=1)
        day_idx += 1

    return rows


def generate_dataset(months: int = 24, seed: int = 42) -> List[Tuple]:
    """Generate the full dataset for all sections over ``months`` months."""
    rng = random.Random(seed)
    end_date = date.today().replace(day=1) - timedelta(days=1)  # last day of previous month
    # start_date = first day of the month `months` ago
    year = end_date.year - (months // 12)
    month = end_date.month - (months % 12)
    if month <= 0:
        month += 12
        year -= 1
    start_date = date(year, month, 1)

    all_rows: List[Tuple] = []
    for section in SECTIONS:
        all_rows.extend(generate_daily_rows(section, start_date, end_date, rng))

    return sorted(all_rows, key=lambda r: (r[1], r[0]))


HEADER = (
    "section_id",
    "metric_date",
    "active_users",
    "api_calls",
    "cpu_usage_pct",
    "memory_usage_gb",
    "storage_usage_gb",
    "pipeline_runs",
    "error_rate_pct",
    "avg_response_ms",
)


def save_csv(rows: List[Tuple], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print(f"Wrote {len(rows):,} rows to {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic platform usage data.")
    parser.add_argument("--months", type=int, default=24, help="Months of history to generate (default: 24)")
    parser.add_argument("--seed",   type=int, default=42,  help="Random seed for reproducibility (default: 42)")
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(__file__), "platform_usage.csv"),
        help="Output CSV path",
    )
    args = parser.parse_args()
    rows = generate_dataset(months=args.months, seed=args.seed)
    save_csv(rows, args.output)


if __name__ == "__main__":
    main()
