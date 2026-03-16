# Tableau Dashboard Documentation

## Product Usage Forecasting Dashboard

This directory documents the Tableau dashboard design used to visualise product usage forecasts and infrastructure scaling needs for GitLab Platform sections.

### Dashboard Pages

1. **Usage Overview**
   - Monthly active users trend by platform section
   - Total API calls and CI/CD minutes over time
   - Storage and compute usage heat-map

2. **Forecast View**
   - Predicted vs. actual usage (with 95% confidence bands)
   - 6-month rolling forecast for each metric
   - Section-level drill-down

3. **Variance Analysis**
   - Monthly variance status tiles (On Track / Minor / Significant / Critical)
   - Variance trend over last 12 months
   - Automated alert indicators

4. **Infrastructure Scaling**
   - Scaling recommendations timeline
   - Capacity utilisation gauges
   - Growth projection waterfall charts

### Data Sources

The dashboard connects to the forecasting database (SQLite for demo; production uses a data warehouse). Key tables:

| Table | Purpose |
|-------|---------|
| `usage_metrics` | Historical daily usage by section |
| `forecasts` | Model predictions with confidence intervals |
| `variance_reports` | Monthly actual-vs-forecast comparisons |

### Refresh Schedule

| Cadence | Action |
|---------|--------|
| Daily | Ingest new usage metrics |
| Monthly | Run forecasting model and variance analysis |
| Monthly | Auto-refresh Tableau extracts |

### How to Reproduce

1. Run the Python pipeline (`python -m src.data_generator` then the forecasting and variance scripts) to populate the SQLite database.
2. Open Tableau Desktop and connect to the generated `.db` file as a SQLite data source.
3. Import the calculated fields and layout described above.
4. Publish to Tableau Server / Tableau Online for shared access.
