-- Product Usage Forecasting - Database Schema
-- Schema for tracking GitLab Platform section usage metrics

CREATE TABLE IF NOT EXISTS platform_sections (
    section_id      INTEGER PRIMARY KEY,
    section_name    VARCHAR(100) NOT NULL,
    description     TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage_metrics (
    metric_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id      INTEGER NOT NULL,
    metric_date     DATE NOT NULL,
    active_users    INTEGER NOT NULL DEFAULT 0,
    api_calls       INTEGER NOT NULL DEFAULT 0,
    ci_minutes      REAL NOT NULL DEFAULT 0,
    storage_gb      REAL NOT NULL DEFAULT 0,
    compute_hours   REAL NOT NULL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (section_id) REFERENCES platform_sections(section_id),
    UNIQUE(section_id, metric_date)
);

CREATE TABLE IF NOT EXISTS forecasts (
    forecast_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id      INTEGER NOT NULL,
    forecast_date   DATE NOT NULL,
    metric_name     VARCHAR(50) NOT NULL,
    predicted_value REAL NOT NULL,
    lower_bound     REAL,
    upper_bound     REAL,
    model_version   VARCHAR(20),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (section_id) REFERENCES platform_sections(section_id)
);

CREATE TABLE IF NOT EXISTS variance_reports (
    report_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id      INTEGER NOT NULL,
    report_month    DATE NOT NULL,
    metric_name     VARCHAR(50) NOT NULL,
    actual_value    REAL NOT NULL,
    forecast_value  REAL NOT NULL,
    variance_pct    REAL NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (section_id) REFERENCES platform_sections(section_id)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_usage_section_date ON usage_metrics(section_id, metric_date);
CREATE INDEX IF NOT EXISTS idx_forecasts_section_date ON forecasts(section_id, forecast_date);
CREATE INDEX IF NOT EXISTS idx_variance_month ON variance_reports(report_month);
