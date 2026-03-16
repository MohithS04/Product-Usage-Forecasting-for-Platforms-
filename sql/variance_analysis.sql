-- =============================================================================
-- Automated Monthly Performance Variance Analysis
-- =============================================================================
-- Run this script monthly (e.g., via a cron job or dbt run) once actuals are
-- available. It computes the difference between what was forecasted vs. what
-- actually occurred and writes results to forecast_variance.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Step 1: Populate forecast_variance for the most recently completed month
-- ---------------------------------------------------------------------------

INSERT INTO forecast_variance (
    section_id,
    year_month,
    forecast_run_date,
    model_version,
    actual_active_users,
    predicted_active_users,
    user_variance_pct,
    actual_api_calls,
    predicted_api_calls,
    api_variance_pct,
    actual_cpu_pct,
    predicted_cpu_pct,
    cpu_variance_pct,
    actual_memory_gb,
    predicted_memory_gb,
    memory_variance_pct,
    overall_accuracy_score
)
SELECT
    a.section_id,
    a.year_month,
    f.forecast_run_date,
    f.model_version,

    -- Actuals
    a.avg_active_users      AS actual_active_users,
    f.predicted_active_users,

    -- User variance %
    ROUND(
        (f.predicted_active_users - a.avg_active_users)
        / NULLIF(a.avg_active_users, 0) * 100, 4
    ) AS user_variance_pct,

    a.total_api_calls       AS actual_api_calls,
    f.predicted_api_calls,

    -- API variance %
    ROUND(
        (f.predicted_api_calls - a.total_api_calls)
        / NULLIF(a.total_api_calls, 0) * 100, 4
    ) AS api_variance_pct,

    a.avg_cpu_usage_pct     AS actual_cpu_pct,
    f.predicted_cpu_usage_pct,

    -- CPU variance %
    ROUND(
        (f.predicted_cpu_usage_pct - a.avg_cpu_usage_pct)
        / NULLIF(a.avg_cpu_usage_pct, 0) * 100, 4
    ) AS cpu_variance_pct,

    a.avg_memory_usage_gb   AS actual_memory_gb,
    f.predicted_memory_gb,

    -- Memory variance %
    ROUND(
        (f.predicted_memory_gb - a.avg_memory_usage_gb)
        / NULLIF(a.avg_memory_usage_gb, 0) * 100, 4
    ) AS memory_variance_pct,

    -- Overall accuracy score: 100 - Mean Absolute Percentage Error across metrics
    ROUND(100.0 - (
        ABS((f.predicted_active_users  - a.avg_active_users)    / NULLIF(a.avg_active_users,  0) * 100)
      + ABS((f.predicted_api_calls     - a.total_api_calls)     / NULLIF(a.total_api_calls,    0) * 100)
      + ABS((f.predicted_cpu_usage_pct - a.avg_cpu_usage_pct)   / NULLIF(a.avg_cpu_usage_pct,  0) * 100)
      + ABS((f.predicted_memory_gb     - a.avg_memory_usage_gb) / NULLIF(a.avg_memory_usage_gb,0) * 100)
    ) / 4.0, 2) AS overall_accuracy_score

FROM monthly_usage_summary a
JOIN usage_forecasts f
    ON  f.section_id     = a.section_id
    AND f.forecast_month = a.year_month
-- Only process the month that just closed
WHERE a.year_month = TO_CHAR(DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month', 'YYYY-MM')
ON CONFLICT (section_id, year_month, forecast_run_date) DO UPDATE
    SET actual_active_users    = EXCLUDED.actual_active_users,
        user_variance_pct      = EXCLUDED.user_variance_pct,
        actual_api_calls       = EXCLUDED.actual_api_calls,
        api_variance_pct       = EXCLUDED.api_variance_pct,
        actual_cpu_pct         = EXCLUDED.actual_cpu_pct,
        cpu_variance_pct       = EXCLUDED.cpu_variance_pct,
        actual_memory_gb       = EXCLUDED.actual_memory_gb,
        memory_variance_pct    = EXCLUDED.memory_variance_pct,
        overall_accuracy_score = EXCLUDED.overall_accuracy_score,
        computed_at            = CURRENT_TIMESTAMP;


-- ---------------------------------------------------------------------------
-- Step 2: Variance Summary Report – current month
-- ---------------------------------------------------------------------------

SELECT
    ps.section_name,
    v.year_month,
    -- Active Users
    v.actual_active_users,
    v.predicted_active_users,
    v.user_variance_pct,
    -- CPU
    v.actual_cpu_pct,
    v.predicted_cpu_pct,
    v.cpu_variance_pct,
    -- Memory
    v.actual_memory_gb,
    v.predicted_memory_gb,
    v.memory_variance_pct,
    -- Overall
    v.overall_accuracy_score,
    CASE
        WHEN v.overall_accuracy_score >= 95 THEN 'Excellent (≥95%)'
        WHEN v.overall_accuracy_score >= 90 THEN 'Good (90–95%)'
        WHEN v.overall_accuracy_score >= 80 THEN 'Acceptable (80–90%)'
        ELSE                                     'Needs Review (<80%)'
    END AS accuracy_band
FROM forecast_variance v
JOIN platform_sections ps ON ps.section_id = v.section_id
WHERE v.year_month = TO_CHAR(DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '1 month', 'YYYY-MM')
ORDER BY v.overall_accuracy_score DESC;


-- ---------------------------------------------------------------------------
-- Step 3: Rolling 12-Month Accuracy Trend per Section
-- ---------------------------------------------------------------------------

SELECT
    ps.section_name,
    v.year_month,
    v.overall_accuracy_score,
    ROUND(AVG(v.overall_accuracy_score) OVER (
        PARTITION BY v.section_id
        ORDER BY v.year_month
        ROWS BETWEEN 11 PRECEDING AND CURRENT ROW
    ), 2) AS rolling_12m_accuracy,
    ROUND(AVG(v.overall_accuracy_score) OVER (
        PARTITION BY v.section_id
        ORDER BY v.year_month
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 2) AS rolling_3m_accuracy
FROM forecast_variance v
JOIN platform_sections ps ON ps.section_id = v.section_id
ORDER BY ps.section_name, v.year_month;


-- ---------------------------------------------------------------------------
-- Step 4: Sections Consistently Exceeding 95% Accuracy (last 6 months)
-- ---------------------------------------------------------------------------

SELECT
    ps.section_name,
    COUNT(*) AS months_evaluated,
    ROUND(AVG(v.overall_accuracy_score), 2) AS avg_accuracy_6m,
    MIN(v.overall_accuracy_score) AS min_accuracy,
    MAX(v.overall_accuracy_score) AS max_accuracy
FROM forecast_variance v
JOIN platform_sections ps ON ps.section_id = v.section_id
WHERE v.year_month >= TO_CHAR(
    DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '6 months', 'YYYY-MM'
)
GROUP BY ps.section_name, v.section_id
HAVING AVG(v.overall_accuracy_score) >= 95
ORDER BY avg_accuracy_6m DESC;


-- ---------------------------------------------------------------------------
-- Step 5: Largest Forecast Misses (for model improvement)
-- ---------------------------------------------------------------------------

SELECT
    ps.section_name,
    v.year_month,
    ABS(v.user_variance_pct)    AS abs_user_error_pct,
    ABS(v.cpu_variance_pct)     AS abs_cpu_error_pct,
    ABS(v.memory_variance_pct)  AS abs_memory_error_pct,
    v.overall_accuracy_score
FROM forecast_variance v
JOIN platform_sections ps ON ps.section_id = v.section_id
WHERE v.overall_accuracy_score < 95
ORDER BY v.overall_accuracy_score ASC
LIMIT 20;
