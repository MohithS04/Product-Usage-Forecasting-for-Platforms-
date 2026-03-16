"""Synthetic data generator for product usage forecasting demonstrations.

Generates realistic historical usage metrics for GitLab Platform sections
with seasonal patterns and growth trends.
"""

import sqlite3
from datetime import date, timedelta

import numpy as np
import pandas as pd

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import DEFAULT_SECTIONS, METRIC_COLUMNS


def create_database(db_path: str) -> sqlite3.Connection:
    """Create a SQLite database and initialize the schema."""
    conn = sqlite3.connect(db_path)
    schema_path = os.path.join(os.path.dirname(__file__), "..", "sql", "schema.sql")
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    return conn


def seed_sections(conn: sqlite3.Connection) -> None:
    """Insert default platform sections into the database."""
    for section in DEFAULT_SECTIONS:
        conn.execute(
            "INSERT OR IGNORE INTO platform_sections (section_id, section_name, description) "
            "VALUES (?, ?, ?)",
            (section["section_id"], section["section_name"], section["description"]),
        )
    conn.commit()


def generate_usage_data(
    num_months: int = 24,
    start_date: date | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic monthly usage data for all platform sections.

    Parameters
    ----------
    num_months : int
        Number of months of historical data to generate.
    start_date : date or None
        Start date for the data.  Defaults to ``num_months`` before today.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: section_id, metric_date, active_users,
        api_calls, ci_minutes, storage_gb, compute_hours.
    """
    rng = np.random.default_rng(seed)

    if start_date is None:
        start_date = date.today().replace(day=1) - timedelta(days=num_months * 30)

    # Base values per section (order matches DEFAULT_SECTIONS)
    base_values = {
        1: {"active_users": 5000, "api_calls": 500000, "ci_minutes": 80000, "storage_gb": 1200, "compute_hours": 3000},
        2: {"active_users": 3000, "api_calls": 200000, "ci_minutes": 20000, "storage_gb": 2500, "compute_hours": 1500},
        3: {"active_users": 2000, "api_calls": 100000, "ci_minutes": 5000,  "storage_gb": 800,  "compute_hours": 600},
        4: {"active_users": 4000, "api_calls": 350000, "ci_minutes": 60000, "storage_gb": 500,  "compute_hours": 5000},
        5: {"active_users": 2500, "api_calls": 150000, "ci_minutes": 10000, "storage_gb": 3000, "compute_hours": 1000},
    }

    rows = []
    for section in DEFAULT_SECTIONS:
        sid = section["section_id"]
        bases = base_values[sid]
        for month_offset in range(num_months):
            current_date = start_date + timedelta(days=month_offset * 30)
            current_date = current_date.replace(day=1)

            # Growth factor: ~3-8 % monthly growth
            growth = (1 + rng.uniform(0.03, 0.08)) ** month_offset

            # Seasonal factor (higher usage in Q4 and Q1)
            month_num = current_date.month
            seasonal = 1.0 + 0.10 * np.sin(2 * np.pi * (month_num - 1) / 12)

            for metric in METRIC_COLUMNS:
                base = bases[metric]
                noise = rng.normal(1.0, 0.03)
                value = base * growth * seasonal * noise

                if metric in ("active_users", "api_calls"):
                    value = int(round(value))
                else:
                    value = round(value, 2)

                rows.append({
                    "section_id": sid,
                    "metric_date": current_date.isoformat(),
                    "metric": metric,
                    "value": value,
                })

    df = pd.DataFrame(rows)
    # Pivot so each metric is a column
    pivot = df.pivot_table(
        index=["section_id", "metric_date"],
        columns="metric",
        values="value",
        aggfunc="first",
    ).reset_index()
    pivot.columns.name = None
    return pivot


def load_usage_data(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    """Load usage data into the database."""
    for _, row in df.iterrows():
        conn.execute(
            "INSERT OR IGNORE INTO usage_metrics "
            "(section_id, metric_date, active_users, api_calls, ci_minutes, storage_gb, compute_hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                int(row["section_id"]),
                row["metric_date"],
                int(row["active_users"]),
                int(row["api_calls"]),
                float(row["ci_minutes"]),
                float(row["storage_gb"]),
                float(row["compute_hours"]),
            ),
        )
    conn.commit()


def setup_demo_database(db_path: str, num_months: int = 24) -> sqlite3.Connection:
    """Create and populate a demo database with synthetic data.

    Returns the open database connection.
    """
    conn = create_database(db_path)
    seed_sections(conn)
    df = generate_usage_data(num_months=num_months)
    load_usage_data(conn, df)
    return conn
