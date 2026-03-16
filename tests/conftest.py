"""
conftest.py
===========
Shared pytest fixtures for the Product Usage Forecasting test suite.

These fixtures are automatically discovered by pytest and available to every
test module in the ``tests/`` directory without needing an explicit import.
"""

from __future__ import annotations

import os
import tempfile
from typing import Generator

import pandas as pd
import pytest

from data.generate_data import generate_dataset, save_csv
from forecasting.model import UsageForecaster, load_monthly_data


# ---------------------------------------------------------------------------
# Session-scoped: generate once, reuse across all tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def daily_csv_path(tmp_path_factory: pytest.TempPathFactory) -> str:
    """
    Generate a 24-month synthetic daily CSV once per test session.

    Returns the absolute path to the CSV file.
    """
    tmp_dir = tmp_path_factory.mktemp("data")
    path = str(tmp_dir / "platform_usage.csv")
    rows = generate_dataset(months=24, seed=42)
    save_csv(rows, path)
    return path


@pytest.fixture(scope="session")
def monthly_df(daily_csv_path: str) -> pd.DataFrame:
    """
    Monthly-aggregated DataFrame loaded from the session-level CSV.
    """
    return load_monthly_data(daily_csv_path)


@pytest.fixture(scope="session")
def train_test_split(monthly_df: pd.DataFrame):
    """
    Return (train_df, test_df) using the last 3 months as holdout.
    """
    all_months = sorted(monthly_df["year_month"].unique())
    train_months = all_months[:-3]
    test_months = all_months[-3:]
    return (
        monthly_df[monthly_df["year_month"].isin(train_months)].copy(),
        monthly_df[monthly_df["year_month"].isin(test_months)].copy(),
    )


@pytest.fixture(scope="session")
def fitted_forecaster(train_test_split) -> UsageForecaster:
    """
    A ``UsageForecaster`` fitted on the training split.
    """
    train_df, _ = train_test_split
    forecaster = UsageForecaster()
    forecaster.fit(train_df)
    return forecaster


@pytest.fixture(scope="session")
def forecast_df(fitted_forecaster: UsageForecaster) -> pd.DataFrame:
    """
    3-month forecast from the session-level fitted forecaster.
    """
    return fitted_forecaster.predict(horizon=3)
