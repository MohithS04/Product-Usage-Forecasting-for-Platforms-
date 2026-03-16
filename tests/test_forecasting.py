"""
tests/test_forecasting.py
=========================
Unit and integration tests for the Product Usage Forecasting pipeline.

Run with:
    pip install -r requirements.txt
    python -m pytest tests/ -v
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

# Make the project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.generate_data import (
    SECTIONS,
    _day_of_week_factor,
    _seasonal_factor,
    generate_dataset,
    save_csv,
)
from forecasting.model import (
    UsageForecaster,
    _add_months,
    _z_score,
    load_monthly_data,
)
from forecasting.variance_analysis import (
    compute_variance,
    monthly_summary,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def daily_csv(tmp_path_factory) -> str:
    """Generate a 24-month daily CSV and return its path."""
    rows = generate_dataset(months=24, seed=42)
    out = str(tmp_path_factory.mktemp("data") / "platform_usage.csv")
    save_csv(rows, out)
    return out


@pytest.fixture(scope="module")
def monthly_df(daily_csv) -> pd.DataFrame:
    return load_monthly_data(daily_csv)


@pytest.fixture(scope="module")
def fitted_forecaster(monthly_df) -> UsageForecaster:
    fc = UsageForecaster()
    fc.fit(monthly_df)
    return fc


@pytest.fixture(scope="module")
def forecast_df(fitted_forecaster) -> pd.DataFrame:
    return fitted_forecaster.predict(horizon=3)


# ---------------------------------------------------------------------------
# data/generate_data.py
# ---------------------------------------------------------------------------


class TestDataGeneration:
    def test_generate_returns_rows(self):
        rows = generate_dataset(months=6, seed=0)
        assert len(rows) > 0

    def test_columns_count(self):
        rows = generate_dataset(months=3, seed=1)
        assert all(len(r) == 10 for r in rows), "Each row must have 10 fields"

    def test_cpu_bounded(self):
        rows = generate_dataset(months=12, seed=7)
        for r in rows:
            cpu = r[4]  # cpu_usage_pct is index 4
            assert 0.0 <= cpu <= 100.0, f"CPU out of range: {cpu}"

    def test_active_users_positive(self):
        rows = generate_dataset(months=6, seed=5)
        for r in rows:
            assert r[2] > 0, "active_users must be positive"

    def test_reproducibility(self):
        r1 = generate_dataset(months=3, seed=42)
        r2 = generate_dataset(months=3, seed=42)
        assert r1 == r2

    def test_seasonal_factor_range(self):
        for month in range(1, 13):
            f = _seasonal_factor(month, peak_month=3, amplitude=0.15)
            assert 0.5 <= f <= 1.6, f"Seasonal factor out of expected range: {f}"

    def test_weekend_factor_lower(self):
        from datetime import date
        # Monday
        f_weekday = _day_of_week_factor(date(2024, 1, 1))
        # Saturday
        f_weekend = _day_of_week_factor(date(2024, 1, 6))
        assert f_weekend < f_weekday

    def test_all_sections_represented(self, daily_csv):
        df = pd.read_csv(daily_csv)
        ids = set(df["section_id"].unique())
        expected = {s["section_id"] for s in SECTIONS}
        assert ids == expected

    def test_save_and_load_csv(self):
        rows = generate_dataset(months=3, seed=99)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            save_csv(rows, path)
            df = pd.read_csv(path)
            assert len(df) == len(rows)
            assert "active_users" in df.columns
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# forecasting/model.py – helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_add_months_simple(self):
        assert _add_months("2024-11", 1) == "2024-12"
        assert _add_months("2024-01", 1) == "2024-02"
        assert _add_months("2024-12", 1) == "2025-01"
        assert _add_months("2023-11", 3) == "2024-02"

    def test_add_months_wrap_year(self):
        assert _add_months("2024-10", 6) == "2025-04"

    def test_z_score_95(self):
        z = _z_score(0.95)
        assert abs(z - 1.96) < 0.01

    def test_z_score_90(self):
        z = _z_score(0.90)
        assert abs(z - 1.645) < 0.01

    def test_z_score_99(self):
        z = _z_score(0.99)
        assert abs(z - 2.576) < 0.01


# ---------------------------------------------------------------------------
# forecasting/model.py – UsageForecaster
# ---------------------------------------------------------------------------


class TestUsageForecaster:
    def test_fit_returns_self(self, monthly_df):
        fc = UsageForecaster()
        result = fc.fit(monthly_df)
        assert result is fc

    def test_is_fitted_after_fit(self, fitted_forecaster):
        assert fitted_forecaster._is_fitted

    def test_predict_before_fit_raises(self):
        with pytest.raises(RuntimeError):
            UsageForecaster().predict()

    def test_forecast_shape(self, forecast_df):
        # 8 sections × 3 months × 4 metrics = 96 rows
        assert len(forecast_df) == 8 * 3 * 4

    def test_forecast_columns(self, forecast_df):
        expected = {"section_name", "forecast_month", "metric", "predicted", "ci_lower", "ci_upper"}
        assert expected.issubset(set(forecast_df.columns))

    def test_forecast_predicted_positive(self, forecast_df):
        assert (forecast_df["predicted"] >= 0).all()

    def test_forecast_ci_ordering(self, forecast_df):
        assert (forecast_df["ci_lower"] <= forecast_df["predicted"]).all()
        assert (forecast_df["predicted"] <= forecast_df["ci_upper"]).all()

    def test_forecast_cpu_capped(self, forecast_df):
        cpu = forecast_df[forecast_df["metric"] == "cpu_usage_pct"]
        assert (cpu["predicted"] <= 100.0).all()
        assert (cpu["ci_upper"] <= 100.0).all()

    def test_forecast_horizon_1(self, monthly_df):
        fc = UsageForecaster().fit(monthly_df)
        df = fc.predict(horizon=1)
        assert df["forecast_month"].nunique() == 1

    def test_forecast_horizon_6(self, monthly_df):
        fc = UsageForecaster().fit(monthly_df)
        df = fc.predict(horizon=6)
        assert df["forecast_month"].nunique() == 6

    def test_all_sections_in_forecast(self, forecast_df, monthly_df):
        trained_sections = set(monthly_df["section_name"].unique())
        forecast_sections = set(forecast_df["section_name"].unique())
        assert trained_sections == forecast_sections

    def test_forecast_months_are_future(self, monthly_df, forecast_df):
        last_actual = monthly_df["year_month"].max()
        for fm in forecast_df["forecast_month"].unique():
            assert fm > last_actual, f"Forecast month {fm} not after last actual {last_actual}"

    def test_evaluate_returns_dataframe(self, monthly_df):
        """evaluate() should return a DataFrame with accuracy columns."""
        all_months = sorted(monthly_df["year_month"].unique())
        train = monthly_df[monthly_df["year_month"].isin(all_months[:-3])]
        test  = monthly_df[monthly_df["year_month"].isin(all_months[-3:])]
        fc = UsageForecaster().fit(train)
        preds = fc.predict(horizon=3)
        result = fc.evaluate(test, preds)
        assert isinstance(result, pd.DataFrame)
        assert "accuracy_score" in result.columns
        assert "overall_accuracy" in result.columns

    def test_scaling_recommendations_columns(self, forecast_df, monthly_df):
        fc = UsageForecaster().fit(monthly_df)
        recs = fc.scaling_recommendations(forecast_df)
        for col in ["section_name", "forecast_month", "urgency", "pm_summary"]:
            assert col in recs.columns

    def test_scaling_recommendation_urgency_values(self, forecast_df, monthly_df):
        fc = UsageForecaster().fit(monthly_df)
        recs = fc.scaling_recommendations(forecast_df)
        valid = {"critical", "high", "medium", "low"}
        assert set(recs["urgency"].unique()).issubset(valid)


# ---------------------------------------------------------------------------
# forecasting/model.py – 95% accuracy integration test
# ---------------------------------------------------------------------------


class TestAccuracyTarget:
    """
    Integration test: train on first 21 months, forecast last 3, verify
    the mean accuracy is ≥ 95 % (project requirement).
    """

    def test_overall_accuracy_meets_95_pct_target(self, monthly_df):
        all_months = sorted(monthly_df["year_month"].unique())
        assert len(all_months) >= 12, "Need at least 12 months for this test"

        train_months = all_months[:-3]
        test_months  = all_months[-3:]

        train_df = monthly_df[monthly_df["year_month"].isin(train_months)]
        test_df  = monthly_df[monthly_df["year_month"].isin(test_months)]

        fc = UsageForecaster().fit(train_df)
        preds = fc.predict(horizon=3)

        # Filter forecasts to only the test period
        preds_test = preds[preds["forecast_month"].isin(test_months)]

        eval_df = fc.evaluate(test_df, preds_test)
        assert not eval_df.empty, "Evaluation returned empty DataFrame"

        global_accuracy = float(eval_df["overall_accuracy"].mean())
        print(f"\n  [Accuracy test] Overall accuracy = {global_accuracy:.2f}%")
        assert global_accuracy >= 95.0, (
            f"Global accuracy {global_accuracy:.2f}% is below the 95% target"
        )

    def test_per_section_accuracy_report(self, monthly_df):
        """All sections should individually meet or be close to 95%."""
        all_months = sorted(monthly_df["year_month"].unique())
        train_df = monthly_df[monthly_df["year_month"].isin(all_months[:-3])]
        test_df  = monthly_df[monthly_df["year_month"].isin(all_months[-3:])]

        fc = UsageForecaster().fit(train_df)
        preds = fc.predict(horizon=3)
        preds_test = preds[preds["forecast_month"].isin(all_months[-3:])]

        eval_df = fc.evaluate(test_df, preds_test)
        by_section = eval_df.groupby("section_name")["overall_accuracy"].first()

        below_90 = by_section[by_section < 90.0]
        assert len(below_90) == 0, (
            f"Sections with accuracy < 90%: {below_90.to_dict()}"
        )


# ---------------------------------------------------------------------------
# forecasting/variance_analysis.py
# ---------------------------------------------------------------------------


class TestVarianceAnalysis:
    @pytest.fixture(scope="class")
    def variance_data(self, monthly_df):
        all_months = sorted(monthly_df["year_month"].unique())
        train_df = monthly_df[monthly_df["year_month"].isin(all_months[:-3])]
        test_df  = monthly_df[monthly_df["year_month"].isin(all_months[-3:])]
        fc = UsageForecaster().fit(train_df)
        preds = fc.predict(horizon=3)
        return test_df, preds

    def test_compute_variance_returns_dataframe(self, variance_data):
        test_df, preds = variance_data
        result = compute_variance(test_df, preds)
        assert isinstance(result, pd.DataFrame)
        assert not result.empty

    def test_compute_variance_columns(self, variance_data):
        test_df, preds = variance_data
        result = compute_variance(test_df, preds)
        for col in ["section_name", "year_month", "metric",
                    "actual", "predicted", "variance_pct", "accuracy_score"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_accuracy_score_range(self, variance_data):
        test_df, preds = variance_data
        result = compute_variance(test_df, preds)
        assert (result["accuracy_score"] >= 0).all()
        assert (result["accuracy_score"] <= 100).all()

    def test_monthly_summary_columns(self, variance_data):
        test_df, preds = variance_data
        var_df = compute_variance(test_df, preds)
        summary = monthly_summary(var_df)
        for col in ["section_name", "year_month", "avg_accuracy", "meets_95_pct_target"]:
            assert col in summary.columns

    def test_within_target_flag(self, variance_data):
        test_df, preds = variance_data
        result = compute_variance(test_df, preds)
        assert result["within_target"].dtype == bool

    def test_variance_run_pipeline(self, daily_csv, tmp_path):
        from forecasting.variance_analysis import run_variance_pipeline
        var_df = run_variance_pipeline(
            csv_path=daily_csv,
            holdout_months=3,
            output_dir=str(tmp_path),
        )
        assert not var_df.empty
        # Reports should be written
        files = os.listdir(str(tmp_path))
        assert any("variance" in f for f in files)


# ---------------------------------------------------------------------------
# load_monthly_data
# ---------------------------------------------------------------------------


class TestLoadMonthlyData:
    def test_returns_dataframe(self, daily_csv):
        df = load_monthly_data(daily_csv)
        assert isinstance(df, pd.DataFrame)

    def test_expected_columns(self, daily_csv):
        df = load_monthly_data(daily_csv)
        for col in ["section_name", "year_month", "active_users", "cpu_usage_pct"]:
            assert col in df.columns

    def test_year_month_format(self, daily_csv):
        df = load_monthly_data(daily_csv)
        for ym in df["year_month"].unique():
            assert len(ym) == 7
            assert ym[4] == "-"

    def test_all_sections_present(self, daily_csv):
        df = load_monthly_data(daily_csv)
        assert df["section_name"].nunique() == len(SECTIONS)

    def test_no_null_metrics(self, daily_csv):
        df = load_monthly_data(daily_csv)
        for col in ["active_users", "cpu_usage_pct", "memory_usage_gb"]:
            assert df[col].isnull().sum() == 0
