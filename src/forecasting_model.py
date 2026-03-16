"""Core forecasting model for product usage prediction.

Uses linear regression with seasonal features to forecast platform usage
metrics over a configurable horizon.
"""

import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    CONFIDENCE_LEVEL,
    FORECAST_HORIZON_MONTHS,
    METRIC_COLUMNS,
    MIN_TRAINING_MONTHS,
)


def _build_features(dates: pd.Series) -> pd.DataFrame:
    """Create time-based and seasonal features from a date series."""
    df = pd.DataFrame()
    base = dates.min()
    df["months_elapsed"] = ((dates - base) / np.timedelta64(30, "D")).astype(float)
    df["month_sin"] = np.sin(2 * np.pi * dates.dt.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * dates.dt.month / 12)
    return df


class UsageForecastModel:
    """Forecasting model for a single metric of a single platform section."""

    def __init__(self) -> None:
        self._model = Ridge(alpha=1.0)
        self._scaler = StandardScaler()
        self._trained = False
        self._residual_std: float = 0.0
        self._base_date: pd.Timestamp | None = None

    @property
    def is_trained(self) -> bool:
        return self._trained

    def train(self, dates: pd.Series, values: pd.Series) -> dict:
        """Train the model on historical data.

        Parameters
        ----------
        dates : pd.Series of datetime64
            Observation dates (monthly granularity expected).
        values : pd.Series of float
            Metric values corresponding to each date.

        Returns
        -------
        dict
            Training summary with keys ``r2_score`` and ``residual_std``.

        Raises
        ------
        ValueError
            If fewer than ``MIN_TRAINING_MONTHS`` data points are provided.
        """
        if len(dates) < MIN_TRAINING_MONTHS:
            raise ValueError(
                f"Need at least {MIN_TRAINING_MONTHS} data points, got {len(dates)}"
            )

        self._base_date = dates.min()
        X = _build_features(dates)
        X_scaled = self._scaler.fit_transform(X)
        y = values.values.astype(float)

        self._model.fit(X_scaled, y)
        predictions = self._model.predict(X_scaled)
        residuals = y - predictions
        self._residual_std = float(np.std(residuals))
        ss_res = float(np.sum(residuals ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        self._trained = True
        return {"r2_score": round(r2, 4), "residual_std": round(self._residual_std, 4)}

    def predict(self, horizon_months: int | None = None) -> pd.DataFrame:
        """Generate forecasts for future months.

        Parameters
        ----------
        horizon_months : int or None
            Number of months to forecast.  Defaults to ``FORECAST_HORIZON_MONTHS``.

        Returns
        -------
        pd.DataFrame
            Columns: forecast_date, predicted_value, lower_bound, upper_bound.
        """
        if not self._trained:
            raise RuntimeError("Model must be trained before predicting.")

        if horizon_months is None:
            horizon_months = FORECAST_HORIZON_MONTHS

        from scipy import stats  # local import to keep dependency optional at module level

        z = stats.norm.ppf((1 + CONFIDENCE_LEVEL) / 2)

        future_dates = pd.date_range(
            start=pd.Timestamp.today().normalize().replace(day=1),
            periods=horizon_months,
            freq="MS",
        )
        future_series = pd.Series(future_dates, name="date")
        X = _build_features(future_series)
        X.iloc[:, 0] = (
            (future_dates - self._base_date) / np.timedelta64(30, "D")
        ).astype(float)
        X_scaled = self._scaler.transform(X)
        preds = self._model.predict(X_scaled)

        lower = preds - z * self._residual_std
        upper = preds + z * self._residual_std

        return pd.DataFrame({
            "forecast_date": future_dates,
            "predicted_value": np.round(preds, 2),
            "lower_bound": np.round(lower, 2),
            "upper_bound": np.round(upper, 2),
        })


def train_all_models(
    usage_df: pd.DataFrame,
) -> dict[tuple[int, str], UsageForecastModel]:
    """Train a forecasting model for each (section, metric) combination.

    Parameters
    ----------
    usage_df : pd.DataFrame
        Must contain ``section_id``, ``metric_date``, and all metric columns.

    Returns
    -------
    dict
        Mapping of ``(section_id, metric_name)`` to trained ``UsageForecastModel``.
    """
    models: dict[tuple[int, str], UsageForecastModel] = {}
    usage_df = usage_df.copy()
    usage_df["metric_date"] = pd.to_datetime(usage_df["metric_date"])

    for section_id in usage_df["section_id"].unique():
        section_data = usage_df[usage_df["section_id"] == section_id].sort_values(
            "metric_date"
        )
        dates = section_data["metric_date"]
        for metric in METRIC_COLUMNS:
            if metric not in section_data.columns:
                continue
            model = UsageForecastModel()
            model.train(dates, section_data[metric])
            models[(int(section_id), metric)] = model

    return models


def generate_all_forecasts(
    models: dict[tuple[int, str], UsageForecastModel],
    horizon_months: int | None = None,
) -> pd.DataFrame:
    """Generate forecasts for all trained models.

    Returns a single DataFrame with columns: section_id, metric_name,
    forecast_date, predicted_value, lower_bound, upper_bound.
    """
    frames = []
    for (section_id, metric_name), model in models.items():
        forecast = model.predict(horizon_months)
        forecast["section_id"] = section_id
        forecast["metric_name"] = metric_name
        frames.append(forecast)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)
