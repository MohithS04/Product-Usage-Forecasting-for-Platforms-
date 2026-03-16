# Product Usage Forecasting for Platforms

A product usage forecasting system that projects infrastructure scaling needs for GitLab Platform sections using historical behavioral data, automated variance analysis, and plain-language reporting.

## Features

- **Usage Forecasting** – Ridge regression model with seasonal features produces 6-month forecasts with 95 % confidence intervals.
- **Automated Variance Analysis** – Monthly comparison of actual vs. forecasted values, categorised by severity, eliminating manual reconciliation.
- **Executive Reporting** – Translates complex analytical findings into simple language for product managers.
- **SQL Analytics** – Ready-to-use queries for data extraction, variance analysis, and infrastructure scaling recommendations.
- **Tableau Integration** – Dashboard documentation for visualising forecasts and scaling needs.

## Project Structure

```
├── config/
│   └── settings.py               # Forecasting parameters and thresholds
├── sql/
│   ├── schema.sql                # Database schema
│   ├── extract_usage_data.sql    # Historical data extraction query
│   ├── monthly_variance_analysis.sql  # Automated variance query
│   └── infrastructure_scaling.sql     # Scaling projection query
├── src/
│   ├── data_generator.py         # Synthetic data generator for demos
│   ├── forecasting_model.py      # Core forecasting model (Ridge + seasonal)
│   ├── variance_analysis.py      # Automated variance analysis engine
│   └── report_generator.py       # Plain-language report generator
├── tableau/
│   └── README.md                 # Tableau dashboard documentation
├── tests/
│   ├── test_data_generator.py
│   ├── test_forecasting_model.py
│   ├── test_variance_analysis.py
│   └── test_report_generator.py
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full pipeline
python -c "
from src.data_generator import generate_usage_data
from src.forecasting_model import train_all_models, generate_all_forecasts
from src.variance_analysis import run_variance_analysis, summarize_variance_report
from src.report_generator import generate_executive_summary

# Generate synthetic data
usage_df = generate_usage_data(num_months=24)

# Train models and forecast
models = train_all_models(usage_df)
forecasts = generate_all_forecasts(models, horizon_months=6)

# Run variance analysis (using last month of historical data as actuals)
last_month = usage_df[usage_df['metric_date'] == usage_df['metric_date'].max()].copy()
last_month = last_month.rename(columns={'metric_date': 'report_month'})
report = run_variance_analysis(last_month, forecasts)
summary = summarize_variance_report(report)

# Generate executive summary
print(generate_executive_summary(forecasts, summary))
"
```

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Dependencies

- Python 3.10+
- pandas, numpy, scikit-learn, scipy