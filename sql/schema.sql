-- =============================================================================
-- Product Usage Forecasting for GitLab Platforms
-- Database Schema
-- =============================================================================

-- Platform sections tracked across the infrastructure
CREATE TABLE IF NOT EXISTS platform_sections (
    section_id      SERIAL PRIMARY KEY,
    section_name    VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    team_owner      VARCHAR(100),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Raw platform usage metrics collected daily
CREATE TABLE IF NOT EXISTS platform_usage_metrics (
    metric_id           SERIAL PRIMARY KEY,
    section_id          INTEGER NOT NULL REFERENCES platform_sections(section_id),
    metric_date         DATE NOT NULL,
    active_users        INTEGER NOT NULL DEFAULT 0,
    api_calls           BIGINT NOT NULL DEFAULT 0,
    cpu_usage_pct       NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    memory_usage_gb     NUMERIC(10,2) NOT NULL DEFAULT 0.0,
    storage_usage_gb    NUMERIC(12,2) NOT NULL DEFAULT 0.0,
    pipeline_runs       INTEGER NOT NULL DEFAULT 0,
    error_rate_pct      NUMERIC(5,2) NOT NULL DEFAULT 0.0,
    avg_response_ms     NUMERIC(10,2) NOT NULL DEFAULT 0.0,
    recorded_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (section_id, metric_date)
);

-- Monthly aggregated usage summary (pre-computed for performance)
CREATE TABLE IF NOT EXISTS monthly_usage_summary (
    summary_id              SERIAL PRIMARY KEY,
    section_id              INTEGER NOT NULL REFERENCES platform_sections(section_id),
    year_month              CHAR(7) NOT NULL,           -- Format: YYYY-MM
    avg_active_users        NUMERIC(12,2),
    total_api_calls         BIGINT,
    avg_cpu_usage_pct       NUMERIC(5,2),
    avg_memory_usage_gb     NUMERIC(10,2),
    avg_storage_usage_gb    NUMERIC(12,2),
    total_pipeline_runs     INTEGER,
    avg_error_rate_pct      NUMERIC(5,2),
    avg_response_ms         NUMERIC(10,2),
    peak_active_users       INTEGER,
    peak_cpu_usage_pct      NUMERIC(5,2),
    computed_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (section_id, year_month)
);

-- Forecasted values produced by the forecasting model
CREATE TABLE IF NOT EXISTS usage_forecasts (
    forecast_id             SERIAL PRIMARY KEY,
    section_id              INTEGER NOT NULL REFERENCES platform_sections(section_id),
    forecast_month          CHAR(7) NOT NULL,           -- Format: YYYY-MM
    forecast_run_date       DATE NOT NULL,
    model_version           VARCHAR(50) NOT NULL DEFAULT '1.0',
    predicted_active_users  NUMERIC(12,2),
    predicted_api_calls     BIGINT,
    predicted_cpu_usage_pct NUMERIC(5,2),
    predicted_memory_gb     NUMERIC(10,2),
    predicted_storage_gb    NUMERIC(12,2),
    confidence_lower        NUMERIC(5,2),               -- 95% CI lower bound
    confidence_upper        NUMERIC(5,2),               -- 95% CI upper bound
    scaling_recommendation  TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (section_id, forecast_month, forecast_run_date)
);

-- Actual vs forecasted variance for monthly performance review
CREATE TABLE IF NOT EXISTS forecast_variance (
    variance_id             SERIAL PRIMARY KEY,
    section_id              INTEGER NOT NULL REFERENCES platform_sections(section_id),
    year_month              CHAR(7) NOT NULL,
    forecast_run_date       DATE NOT NULL,
    model_version           VARCHAR(50) NOT NULL DEFAULT '1.0',
    -- Active users
    actual_active_users     NUMERIC(12,2),
    predicted_active_users  NUMERIC(12,2),
    user_variance_pct       NUMERIC(8,4),
    -- API calls
    actual_api_calls        BIGINT,
    predicted_api_calls     BIGINT,
    api_variance_pct        NUMERIC(8,4),
    -- CPU
    actual_cpu_pct          NUMERIC(5,2),
    predicted_cpu_pct       NUMERIC(5,2),
    cpu_variance_pct        NUMERIC(8,4),
    -- Memory
    actual_memory_gb        NUMERIC(10,2),
    predicted_memory_gb     NUMERIC(10,2),
    memory_variance_pct     NUMERIC(8,4),
    -- Overall accuracy score (MAPE-based, 100 = perfect)
    overall_accuracy_score  NUMERIC(6,2),
    computed_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (section_id, year_month, forecast_run_date)
);

-- Infrastructure scaling recommendations
CREATE TABLE IF NOT EXISTS scaling_recommendations (
    rec_id                  SERIAL PRIMARY KEY,
    section_id              INTEGER NOT NULL REFERENCES platform_sections(section_id),
    recommendation_month    CHAR(7) NOT NULL,
    generated_date          DATE NOT NULL,
    current_capacity_units  INTEGER,
    recommended_capacity    INTEGER,
    scaling_direction       VARCHAR(10) CHECK (scaling_direction IN ('scale_up','scale_down','maintain')),
    urgency_level           VARCHAR(10) CHECK (urgency_level IN ('low','medium','high','critical')),
    estimated_cost_impact   NUMERIC(12,2),
    rationale               TEXT,
    pm_summary              TEXT,                       -- Plain-language summary for product managers
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (section_id, recommendation_month, generated_date)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_metrics_section_date   ON platform_usage_metrics (section_id, metric_date);
CREATE INDEX IF NOT EXISTS idx_metrics_date           ON platform_usage_metrics (metric_date);
CREATE INDEX IF NOT EXISTS idx_monthly_section_month  ON monthly_usage_summary (section_id, year_month);
CREATE INDEX IF NOT EXISTS idx_forecast_section_month ON usage_forecasts (section_id, forecast_month);
CREATE INDEX IF NOT EXISTS idx_variance_section_month ON forecast_variance (section_id, year_month);
CREATE INDEX IF NOT EXISTS idx_scaling_section_month  ON scaling_recommendations (section_id, recommendation_month);
