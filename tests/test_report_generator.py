"""Tests for the report generator."""

import pandas as pd
import pytest

from src.report_generator import (
    generate_executive_summary,
    generate_section_detail,
    _format_number,
    _section_name,
)


class TestFormatNumber:
    def test_millions(self):
        assert _format_number(2_500_000) == "2.5M"

    def test_thousands(self):
        assert _format_number(3_500) == "3.5K"

    def test_small(self):
        assert _format_number(42.7) == "42.7"


class TestSectionName:
    def test_known_section(self):
        assert _section_name(1) == "CI/CD"

    def test_unknown_section(self):
        assert _section_name(999) == "Section 999"


class TestGenerateExecutiveSummary:
    @pytest.fixture
    def forecasts_df(self):
        return pd.DataFrame([
            {"section_id": 1, "metric_name": "active_users", "forecast_date": "2025-01-01",
             "predicted_value": 5000, "lower_bound": 4800, "upper_bound": 5200},
            {"section_id": 1, "metric_name": "active_users", "forecast_date": "2025-06-01",
             "predicted_value": 6000, "lower_bound": 5700, "upper_bound": 6300},
            {"section_id": 1, "metric_name": "compute_hours", "forecast_date": "2025-01-01",
             "predicted_value": 9000, "lower_bound": 8500, "upper_bound": 11000},
            {"section_id": 1, "metric_name": "compute_hours", "forecast_date": "2025-06-01",
             "predicted_value": 12000, "lower_bound": 11000, "upper_bound": 13000},
        ])

    @pytest.fixture
    def variance_summary(self):
        return {
            "total_metrics": 5,
            "on_track_count": 4,
            "deviation_count": 1,
            "avg_absolute_variance": 4.5,
            "worst_metric": {
                "section_id": 1,
                "metric_name": "api_calls",
                "variance_pct": 12.0,
            },
        }

    def test_returns_string(self, forecasts_df, variance_summary):
        result = generate_executive_summary(forecasts_df, variance_summary)
        assert isinstance(result, str)
        assert "EXECUTIVE SUMMARY" in result

    def test_includes_accuracy(self, forecasts_df, variance_summary):
        result = generate_executive_summary(forecasts_df, variance_summary)
        assert "accuracy" in result.lower() or "variance" in result.lower()

    def test_includes_scaling(self, forecasts_df, variance_summary):
        result = generate_executive_summary(forecasts_df, variance_summary)
        assert "SCALING" in result

    def test_empty_forecasts(self, variance_summary):
        result = generate_executive_summary(pd.DataFrame(), variance_summary)
        assert "No forecast data" in result


class TestGenerateSectionDetail:
    def test_returns_section_info(self):
        forecasts = pd.DataFrame([
            {"section_id": 1, "metric_name": "active_users", "forecast_date": "2025-01-01",
             "predicted_value": 5000, "lower_bound": 4800, "upper_bound": 5200},
            {"section_id": 1, "metric_name": "active_users", "forecast_date": "2025-06-01",
             "predicted_value": 6000, "lower_bound": 5700, "upper_bound": 6300},
        ])
        variance = pd.DataFrame()
        result = generate_section_detail(1, forecasts, variance)
        assert "CI/CD" in result
        assert "active_users" in result

    def test_no_data_for_section(self):
        forecasts = pd.DataFrame(
            columns=["section_id", "metric_name", "forecast_date", "predicted_value", "lower_bound", "upper_bound"]
        )
        variance = pd.DataFrame()
        result = generate_section_detail(1, forecasts, variance)
        assert "No forecast data" in result
