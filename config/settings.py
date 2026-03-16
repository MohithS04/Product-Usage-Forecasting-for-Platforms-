"""Configuration settings for the Product Usage Forecasting system."""

# Forecasting parameters
FORECAST_HORIZON_MONTHS = 6
CONFIDENCE_LEVEL = 0.95
MIN_TRAINING_MONTHS = 6

# Metric columns used for forecasting
METRIC_COLUMNS = [
    "active_users",
    "api_calls",
    "ci_minutes",
    "storage_gb",
    "compute_hours",
]

# Variance analysis thresholds (percentage)
VARIANCE_THRESHOLDS = {
    "on_track": 5.0,
    "minor_deviation": 10.0,
    "significant_deviation": 20.0,
}

# Platform sections tracked
DEFAULT_SECTIONS = [
    {"section_id": 1, "section_name": "CI/CD", "description": "Continuous Integration and Delivery"},
    {"section_id": 2, "section_name": "Package Registry", "description": "Package management and container registry"},
    {"section_id": 3, "section_name": "GitLab Pages", "description": "Static site hosting"},
    {"section_id": 4, "section_name": "Runner Fleet", "description": "CI/CD runner infrastructure"},
    {"section_id": 5, "section_name": "Container Registry", "description": "Docker container image storage"},
]
