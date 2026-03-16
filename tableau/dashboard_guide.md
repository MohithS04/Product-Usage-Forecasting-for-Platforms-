# Tableau Dashboard Setup Guide
## Product Usage Forecasting for GitLab Platforms

---

## Overview

This guide explains how to connect Tableau Desktop / Tableau Public to the
data exports produced by the forecasting pipeline and build the four core
dashboards.

---

## Data Sources

Run the pipeline once to generate the CSV exports, then connect each one as a
Tableau data source.

```bash
# Generate sample historical data
python data/generate_data.py

# Run variance analysis + generate report + export CSVs
python forecasting/report_generator.py
```

The following CSV files are written to `reports/`:

| File | Contents | Tableau use |
|------|----------|-------------|
| `actuals_YYYY-MM-DD.csv` | Monthly actual platform metrics | Historical trend charts |
| `forecasts_YYYY-MM-DD.csv` | 3-month-ahead forecasts (long format) | Forecast overlays |
| `variance_YYYY-MM-DD.csv` | Forecast vs actual variance per metric | Accuracy dashboards |

---

## Dashboard 1 – Platform Load Overview

**Purpose**: Give product managers an at-a-glance view of current platform health.

### Steps

1. Connect to `actuals_YYYY-MM-DD.csv`.
2. Create a **line chart**:
   - Columns: `year_month` (continuous date)
   - Rows: `active_users` (average)
   - Color: `section_name`
   - Filter: last 6 months
3. Add a **reference line** at the global average.
4. Duplicate the sheet, replace `active_users` with `cpu_usage_pct`.
5. Arrange both sheets in a dashboard layout titled **"Platform Load Overview"**.

**Key insight for PMs**: Spot which sections are growing fastest and where
CPU headroom is shrinking.

---

## Dashboard 2 – 3-Month Forecast

**Purpose**: Show what the model expects over the next 3 months.

### Steps

1. Connect to `forecasts_YYYY-MM-DD.csv`.
2. Filter `metric` = `active_users`.
3. Create a **bar + line combo chart**:
   - Bar: `predicted` (sum) per `forecast_month`, colored by `section_name`
   - Line overlay: `ci_lower` and `ci_upper` (95 % prediction interval bands)
4. Duplicate the sheet for `cpu_usage_pct`.
5. Add a **color-coded highlight table** showing urgency:
   - Red  (≥ 85 %) – scale up immediately
   - Orange (70–85 %) – plan within current sprint
   - Yellow (55–70 %) – monitor
   - Green (< 55 %) – comfortable

**Key insight for PMs**: Understand which sections need infrastructure
investment before load peaks occur.

---

## Dashboard 3 – Forecast Accuracy (Variance Analysis)

**Purpose**: Build stakeholder confidence by showing model accuracy over time.

### Steps

1. Connect to `variance_YYYY-MM-DD.csv`.
2. Create a **bullet chart**:
   - Target line at 95 % accuracy
   - Actual bars = `accuracy_score` per section
   - Color: green ≥ 95 %, amber 90–95 %, red < 90 %
3. Add a **scatter plot**:
   - X = `actual`, Y = `predicted` per metric
   - Reference line at y = x (perfect forecast)
   - Tooltip: `variance_pct`, `accuracy_score`
4. Add a **filter action** so clicking a section highlights it across all sheets.

**Key insight for PMs**: The model consistently achieves ≥ 95 % accuracy,
making forecasts reliable enough to drive roadmap and infrastructure decisions.

---

## Dashboard 4 – Infrastructure Scaling Recommendations

**Purpose**: Translate forecast findings into actionable capacity decisions.

### Steps

1. Connect to `forecasts_YYYY-MM-DD.csv`.
2. Create a **text table** (highlight table):
   - Rows: `section_name`
   - Columns: `forecast_month`
   - Values: `predicted` for `cpu_usage_pct`
   - Color encoding: red / orange / yellow / green (same thresholds as Dashboard 2)
3. Add a **calculated field** `Scaling Action`:
   ```
   IF [Predicted CPU] >= 85 THEN "🔴 Scale Up Immediately"
   ELSEIF [Predicted CPU] >= 70 THEN "🟠 Plan This Sprint"
   ELSEIF [Predicted CPU] >= 55 THEN "🟡 Monitor"
   ELSE "🟢 No Action"
   END
   ```
4. Show `pm_summary` (from `scaling_recommendations` export) as a tooltip
   or in a text pane for non-technical stakeholders.

**Key insight for PMs**: Each cell communicates urgency in plain language,
enabling evidence-based roadmapping without needing to interpret raw numbers.

---

## Publishing to Tableau Server / Online

1. File → Publish Data Source → choose your server.
2. Set a **refresh schedule** (recommended: 1st day of each month after the
   pipeline runs).
3. Share the workbook URL with product managers and engineering leads.

---

## Recommended Dashboard Layout (Storyboard)

```
┌─────────────────────────────────────────────────────────┐
│  Story Point 1 – Platform Load Overview                 │
├─────────────────────────────────────────────────────────┤
│  Story Point 2 – 3-Month Forecast                       │
├─────────────────────────────────────────────────────────┤
│  Story Point 3 – Forecast Accuracy                      │
├─────────────────────────────────────────────────────────┤
│  Story Point 4 – Scaling Recommendations                │
└─────────────────────────────────────────────────────────┘
```

Present these as a Tableau Story to walk stakeholders through the narrative
from "what happened" → "what we predict" → "how accurate are we" → "what
should we do".

---

## Color Reference

| Color | Hex     | Meaning |
|-------|---------|---------|
| 🟢 Green  | `#4CAF50` | Healthy / no action |
| 🟡 Yellow | `#FFC107` | Monitor |
| 🟠 Orange | `#FF9800` | Action required |
| 🔴 Red    | `#F44336` | Immediate attention |

---

*For pipeline questions, see the [README](../README.md).*
