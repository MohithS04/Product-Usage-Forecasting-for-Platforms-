"""Tests for variance analysis."""

import pandas as pd
import pytest

from src.variance_analysis import (
    classify_variance,
    compute_variance,
    run_variance_analysis,
    summarize_variance_report,
)


class TestComputeVariance:
    def test_positive_variance(self):
        assert compute_variance(110, 100) == 10.0

    def test_negative_variance(self):
        assert compute_variance(90, 100) == -10.0

    def test_zero_forecast(self):
        assert compute_variance(100, 0) == 0.0

    def test_exact_match(self):
        assert compute_variance(100, 100) == 0.0


class TestClassifyVariance:
    def test_on_track(self):
        assert classify_variance(3.0) == "On Track"
        assert classify_variance(-4.5) == "On Track"

    def test_minor_deviation(self):
        assert classify_variance(7.0) == "Minor Deviation"

    def test_significant_deviation(self):
        assert classify_variance(15.0) == "Significant Deviation"

    def test_critical_deviation(self):
        assert classify_variance(25.0) == "Critical Deviation"
        assert classify_variance(-30.0) == "Critical Deviation"


class TestRunVarianceAnalysis:
    @pytest.fixture
    def actuals(self):
        return pd.DataFrame([
            {
                "section_id": 1,
                "report_month": "2025-01-01",
                "active_users": 5200,
                "api_calls": 520000,
                "ci_minutes": 82000,
                "storage_gb": 1250,
                "compute_hours": 3100,
            }
        ])

    @pytest.fixture
    def forecasts(self):
        return pd.DataFrame([
            {"section_id": 1, "metric_name": "active_users",  "forecast_date": "2025-01-01", "predicted_value": 5000},
            {"section_id": 1, "metric_name": "api_calls",     "forecast_date": "2025-01-01", "predicted_value": 500000},
            {"section_id": 1, "metric_name": "ci_minutes",    "forecast_date": "2025-01-01", "predicted_value": 80000},
            {"section_id": 1, "metric_name": "storage_gb",    "forecast_date": "2025-01-01", "predicted_value": 1200},
            {"section_id": 1, "metric_name": "compute_hours", "forecast_date": "2025-01-01", "predicted_value": 3000},
        ])

    def test_returns_results(self, actuals, forecasts):
        report = run_variance_analysis(actuals, forecasts)
        assert len(report) == 5  # one per metric

    def test_variance_values(self, actuals, forecasts):
        report = run_variance_analysis(actuals, forecasts)
        users_row = report[report["metric_name"] == "active_users"].iloc[0]
        assert users_row["variance_pct"] == 4.0  # (5200 - 5000) / 5000 * 100

    def test_status_assigned(self, actuals, forecasts):
        report = run_variance_analysis(actuals, forecasts)
        assert all(report["status"].isin([
            "On Track", "Minor Deviation", "Significant Deviation", "Critical Deviation"
        ]))


class TestSummarizeVarianceReport:
    def test_empty_report(self):
        summary = summarize_variance_report(pd.DataFrame())
        assert summary["total_metrics"] == 0

    def test_summary_keys(self):
        report = pd.DataFrame([
            {"section_id": 1, "metric_name": "active_users", "variance_pct": 3.0, "status": "On Track"},
            {"section_id": 1, "metric_name": "api_calls", "variance_pct": -12.0, "status": "Significant Deviation"},
        ])
        summary = summarize_variance_report(report)
        assert summary["total_metrics"] == 2
        assert summary["on_track_count"] == 1
        assert summary["deviation_count"] == 1
        assert summary["worst_metric"]["metric_name"] == "api_calls"
