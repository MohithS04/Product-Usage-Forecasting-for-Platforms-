"""Tests for the forecasting model."""

import numpy as np
import pandas as pd
import pytest

from src.data_generator import generate_usage_data
from src.forecasting_model import (
    UsageForecastModel,
    generate_all_forecasts,
    train_all_models,
)
from config.settings import FORECAST_HORIZON_MONTHS, METRIC_COLUMNS


@pytest.fixture
def sample_data():
    return generate_usage_data(num_months=12, seed=42)


class TestUsageForecastModel:
    def test_train_requires_minimum_data(self):
        model = UsageForecastModel()
        dates = pd.Series(pd.date_range("2024-01-01", periods=3, freq="MS"))
        values = pd.Series([100, 110, 120])
        with pytest.raises(ValueError, match="at least"):
            model.train(dates, values)

    def test_train_succeeds_with_enough_data(self):
        model = UsageForecastModel()
        dates = pd.Series(pd.date_range("2024-01-01", periods=12, freq="MS"))
        values = pd.Series(range(1000, 1120, 10))
        result = model.train(dates, values)
        assert "r2_score" in result
        assert "residual_std" in result
        assert model.is_trained

    def test_predict_raises_without_training(self):
        model = UsageForecastModel()
        with pytest.raises(RuntimeError, match="trained"):
            model.predict()

    def test_predict_returns_correct_shape(self):
        model = UsageForecastModel()
        dates = pd.Series(pd.date_range("2024-01-01", periods=12, freq="MS"))
        values = pd.Series(range(1000, 1120, 10))
        model.train(dates, values)
        forecast = model.predict(horizon_months=6)
        assert len(forecast) == 6
        assert set(forecast.columns) == {
            "forecast_date",
            "predicted_value",
            "lower_bound",
            "upper_bound",
        }

    def test_confidence_bounds_ordering(self):
        model = UsageForecastModel()
        dates = pd.Series(pd.date_range("2024-01-01", periods=12, freq="MS"))
        values = pd.Series(np.linspace(1000, 2000, 12))
        model.train(dates, values)
        forecast = model.predict(horizon_months=3)
        assert (forecast["lower_bound"] <= forecast["predicted_value"]).all()
        assert (forecast["predicted_value"] <= forecast["upper_bound"]).all()


class TestTrainAllModels:
    def test_trains_model_per_section_metric(self, sample_data):
        models = train_all_models(sample_data)
        sections = sample_data["section_id"].unique()
        expected_count = len(sections) * len(METRIC_COLUMNS)
        assert len(models) == expected_count

    def test_all_models_are_trained(self, sample_data):
        models = train_all_models(sample_data)
        for model in models.values():
            assert model.is_trained


class TestGenerateAllForecasts:
    def test_returns_dataframe(self, sample_data):
        models = train_all_models(sample_data)
        forecasts = generate_all_forecasts(models, horizon_months=3)
        assert isinstance(forecasts, pd.DataFrame)
        assert len(forecasts) > 0

    def test_forecast_columns(self, sample_data):
        models = train_all_models(sample_data)
        forecasts = generate_all_forecasts(models, horizon_months=3)
        required = {
            "section_id",
            "metric_name",
            "forecast_date",
            "predicted_value",
            "lower_bound",
            "upper_bound",
        }
        assert required.issubset(set(forecasts.columns))
