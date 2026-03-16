-- =============================================================================
-- Product Usage Forecasting for GitLab Platforms
-- SQL Forecasting Queries
-- =============================================================================
-- These queries implement the SQL-side of the forecasting pipeline.
-- They compute moving averages, growth trends, seasonal indices, and
-- projected values for the next N months.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Compute Monthly Usage Summary from Raw Daily Metrics
-- ---------------------------------------------------------------------------
-- Run this after new daily data has been loaded to refresh the summary table.

INSERT INTO monthly_usage_summary (
    section_id,
    year_month,
    avg_active_users,
    total_api_calls,
    avg_cpu_usage_pct,
    avg_memory_usage_gb,
    avg_storage_usage_gb,
    total_pipeline_runs,
    avg_error_rate_pct,
    avg_response_ms,
    peak_active_users,
    peak_cpu_usage_pct
)
SELECT
    section_id,
    TO_CHAR(metric_date, 'YYYY-MM')                 AS year_month,
    ROUND(AVG(active_users), 2)                     AS avg_active_users,
    SUM(api_calls)                                  AS total_api_calls,
    ROUND(AVG(cpu_usage_pct), 2)                    AS avg_cpu_usage_pct,
    ROUND(AVG(memory_usage_gb), 2)                  AS avg_memory_usage_gb,
    ROUND(AVG(storage_usage_gb), 2)                 AS avg_storage_usage_gb,
    SUM(pipeline_runs)                              AS total_pipeline_runs,
    ROUND(AVG(error_rate_pct), 2)                   AS avg_error_rate_pct,
    ROUND(AVG(avg_response_ms), 2)                  AS avg_response_ms,
    MAX(active_users)                               AS peak_active_users,
    ROUND(MAX(cpu_usage_pct), 2)                    AS peak_cpu_usage_pct
FROM platform_usage_metrics
GROUP BY section_id, TO_CHAR(metric_date, 'YYYY-MM')
ON CONFLICT (section_id, year_month) DO UPDATE
    SET avg_active_users    = EXCLUDED.avg_active_users,
        total_api_calls     = EXCLUDED.total_api_calls,
        avg_cpu_usage_pct   = EXCLUDED.avg_cpu_usage_pct,
        avg_memory_usage_gb = EXCLUDED.avg_memory_usage_gb,
        avg_storage_usage_gb= EXCLUDED.avg_storage_usage_gb,
        total_pipeline_runs = EXCLUDED.total_pipeline_runs,
        avg_error_rate_pct  = EXCLUDED.avg_error_rate_pct,
        avg_response_ms     = EXCLUDED.avg_response_ms,
        peak_active_users   = EXCLUDED.peak_active_users,
        peak_cpu_usage_pct  = EXCLUDED.peak_cpu_usage_pct,
        computed_at         = CURRENT_TIMESTAMP;


-- ---------------------------------------------------------------------------
-- 2. Trailing 3-Month Moving Average (smoothed baseline)
-- ---------------------------------------------------------------------------

WITH moving_avg AS (
    SELECT
        s.section_name,
        m.year_month,
        m.avg_active_users,
        m.avg_cpu_usage_pct,
        m.avg_memory_usage_gb,
        ROUND(AVG(m.avg_active_users)   OVER w, 2) AS ma3_active_users,
        ROUND(AVG(m.avg_cpu_usage_pct)  OVER w, 2) AS ma3_cpu_pct,
        ROUND(AVG(m.avg_memory_usage_gb)OVER w, 2) AS ma3_memory_gb
    FROM monthly_usage_summary m
    JOIN platform_sections s ON s.section_id = m.section_id
    WINDOW w AS (
        PARTITION BY m.section_id
        ORDER BY m.year_month
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
)
SELECT * FROM moving_avg
ORDER BY section_name, year_month;


-- ---------------------------------------------------------------------------
-- 3. Month-over-Month Growth Rate per Section
-- ---------------------------------------------------------------------------

WITH mom_growth AS (
    SELECT
        s.section_name,
        m.year_month,
        m.avg_active_users,
        LAG(m.avg_active_users) OVER (PARTITION BY m.section_id ORDER BY m.year_month) AS prev_users,
        ROUND(
            (m.avg_active_users - LAG(m.avg_active_users) OVER (PARTITION BY m.section_id ORDER BY m.year_month))
            / NULLIF(LAG(m.avg_active_users) OVER (PARTITION BY m.section_id ORDER BY m.year_month), 0)
            * 100, 4
        ) AS user_growth_pct,
        ROUND(
            (m.avg_cpu_usage_pct - LAG(m.avg_cpu_usage_pct) OVER (PARTITION BY m.section_id ORDER BY m.year_month))
            / NULLIF(LAG(m.avg_cpu_usage_pct) OVER (PARTITION BY m.section_id ORDER BY m.year_month), 0)
            * 100, 4
        ) AS cpu_growth_pct
    FROM monthly_usage_summary m
    JOIN platform_sections s ON s.section_id = m.section_id
)
SELECT * FROM mom_growth
WHERE prev_users IS NOT NULL
ORDER BY section_name, year_month;


-- ---------------------------------------------------------------------------
-- 4. Seasonal Index (month-of-year average vs overall average)
-- ---------------------------------------------------------------------------
-- Values > 1.0 indicate above-average months; < 1.0 below-average.

WITH monthly_avg AS (
    SELECT
        m.section_id,
        EXTRACT(MONTH FROM TO_DATE(m.year_month, 'YYYY-MM'))::INT AS month_num,
        AVG(m.avg_active_users) AS season_avg_users,
        AVG(m.avg_cpu_usage_pct) AS season_avg_cpu
    FROM monthly_usage_summary m
    GROUP BY m.section_id, EXTRACT(MONTH FROM TO_DATE(m.year_month, 'YYYY-MM'))
),
overall_avg AS (
    SELECT
        section_id,
        AVG(avg_active_users) AS overall_avg_users,
        AVG(avg_cpu_usage_pct) AS overall_avg_cpu
    FROM monthly_usage_summary
    GROUP BY section_id
)
SELECT
    ps.section_name,
    ma.month_num,
    TO_CHAR(TO_DATE(ma.month_num::TEXT, 'MM'), 'Month') AS month_name,
    ROUND(ma.season_avg_users  / NULLIF(oa.overall_avg_users, 0), 4) AS seasonal_index_users,
    ROUND(ma.season_avg_cpu    / NULLIF(oa.overall_avg_cpu,   0), 4) AS seasonal_index_cpu
FROM monthly_avg ma
JOIN overall_avg oa ON oa.section_id = ma.section_id
JOIN platform_sections ps ON ps.section_id = ma.section_id
ORDER BY ps.section_name, ma.month_num;


-- ---------------------------------------------------------------------------
-- 5. Linear Trend Coefficients via Least-Squares Regression (SQL)
-- ---------------------------------------------------------------------------
-- Computes slope and intercept for active_users over time.
-- month_index = 1, 2, 3, ... ordered chronologically per section.

WITH indexed AS (
    SELECT
        section_id,
        year_month,
        ROW_NUMBER() OVER (PARTITION BY section_id ORDER BY year_month) AS t,
        avg_active_users  AS y
    FROM monthly_usage_summary
),
sums AS (
    SELECT
        section_id,
        COUNT(*)       AS n,
        SUM(t)         AS sum_t,
        SUM(y)         AS sum_y,
        SUM(t * t)     AS sum_t2,
        SUM(t * y)     AS sum_ty
    FROM indexed
    GROUP BY section_id
)
SELECT
    ps.section_name,
    n,
    ROUND(
        (n * sum_ty - sum_t * sum_y) / NULLIF(n * sum_t2 - sum_t * sum_t, 0)
    , 4) AS slope,
    ROUND(
        (sum_y - ((n * sum_ty - sum_t * sum_y) / NULLIF(n * sum_t2 - sum_t * sum_t, 0)) * sum_t) / n
    , 4) AS intercept
FROM sums
JOIN platform_sections ps ON ps.section_id = sums.section_id
ORDER BY ps.section_name;


-- ---------------------------------------------------------------------------
-- 6. 3-Month Ahead Forecast using Trend + Seasonality
-- ---------------------------------------------------------------------------
-- Combines the linear trend slope with seasonal indices to produce
-- month-level forecasts for the next 3 calendar months.

WITH indexed AS (
    SELECT
        section_id,
        year_month,
        ROW_NUMBER() OVER (PARTITION BY section_id ORDER BY year_month) AS t,
        avg_active_users AS y,
        avg_cpu_usage_pct AS y_cpu,
        avg_memory_usage_gb AS y_mem
    FROM monthly_usage_summary
),
trend AS (
    SELECT
        section_id,
        COUNT(*)          AS n,
        -- Active users trend
        (COUNT(*) * SUM(t * y) - SUM(t) * SUM(y))
          / NULLIF(COUNT(*) * SUM(t * t) - SUM(t) * SUM(t), 0) AS slope_users,
        (SUM(y) - ((COUNT(*) * SUM(t * y) - SUM(t) * SUM(y))
          / NULLIF(COUNT(*) * SUM(t * t) - SUM(t) * SUM(t), 0)) * SUM(t)) / COUNT(*) AS intercept_users,
        -- CPU trend
        (COUNT(*) * SUM(t * y_cpu) - SUM(t) * SUM(y_cpu))
          / NULLIF(COUNT(*) * SUM(t * t) - SUM(t) * SUM(t), 0) AS slope_cpu,
        (SUM(y_cpu) - ((COUNT(*) * SUM(t * y_cpu) - SUM(t) * SUM(y_cpu))
          / NULLIF(COUNT(*) * SUM(t * t) - SUM(t) * SUM(t), 0)) * SUM(t)) / COUNT(*) AS intercept_cpu,
        -- Memory trend
        (COUNT(*) * SUM(t * y_mem) - SUM(t) * SUM(y_mem))
          / NULLIF(COUNT(*) * SUM(t * t) - SUM(t) * SUM(t), 0) AS slope_mem,
        (SUM(y_mem) - ((COUNT(*) * SUM(t * y_mem) - SUM(t) * SUM(y_mem))
          / NULLIF(COUNT(*) * SUM(t * t) - SUM(t) * SUM(t), 0)) * SUM(t)) / COUNT(*) AS intercept_mem
    FROM indexed
    GROUP BY section_id
),
max_t AS (
    SELECT section_id, MAX(t) AS max_index FROM indexed GROUP BY section_id
),
seasonal AS (
    SELECT
        m.section_id,
        EXTRACT(MONTH FROM TO_DATE(m.year_month, 'YYYY-MM'))::INT AS month_num,
        AVG(m.avg_active_users) / NULLIF(AVG(AVG(m.avg_active_users)) OVER (PARTITION BY m.section_id), 0) AS si_users,
        AVG(m.avg_cpu_usage_pct) / NULLIF(AVG(AVG(m.avg_cpu_usage_pct)) OVER (PARTITION BY m.section_id), 0) AS si_cpu,
        AVG(m.avg_memory_usage_gb) / NULLIF(AVG(AVG(m.avg_memory_usage_gb)) OVER (PARTITION BY m.section_id), 0) AS si_mem
    FROM monthly_usage_summary m
    GROUP BY m.section_id, EXTRACT(MONTH FROM TO_DATE(m.year_month, 'YYYY-MM'))
),
horizon AS (
    -- Generate t+1, t+2, t+3 forecast points
    SELECT mt.section_id, mt.max_index + gs.n AS future_t,
           gs.n AS horizon_offset
    FROM max_t mt
    CROSS JOIN (SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3) gs
),
latest_month AS (
    SELECT section_id, MAX(year_month) AS last_month
    FROM monthly_usage_summary
    GROUP BY section_id
)
SELECT
    ps.section_name,
    TO_CHAR(
        (TO_DATE(lm.last_month, 'YYYY-MM') + (h.horizon_offset || ' month')::INTERVAL),
        'YYYY-MM'
    ) AS forecast_month,
    ROUND((tr.intercept_users + tr.slope_users * h.future_t) * COALESCE(s.si_users, 1.0), 0)   AS predicted_active_users,
    LEAST(100.0,
      ROUND((tr.intercept_cpu   + tr.slope_cpu   * h.future_t) * COALESCE(s.si_cpu,   1.0), 2)) AS predicted_cpu_pct,
    ROUND((tr.intercept_mem   + tr.slope_mem   * h.future_t) * COALESCE(s.si_mem,   1.0), 2)   AS predicted_memory_gb
FROM horizon h
JOIN trend tr ON tr.section_id = h.section_id
JOIN latest_month lm ON lm.section_id = h.section_id
JOIN platform_sections ps ON ps.section_id = h.section_id
LEFT JOIN seasonal s
    ON s.section_id = h.section_id
    AND s.month_num = EXTRACT(MONTH FROM
        TO_DATE(lm.last_month, 'YYYY-MM') + (h.horizon_offset || ' month')::INTERVAL
    )::INT
ORDER BY ps.section_name, forecast_month;


-- ---------------------------------------------------------------------------
-- 7. Infrastructure Scaling Threshold Check
-- ---------------------------------------------------------------------------
-- Flags any section where the next-month forecast exceeds capacity thresholds.

WITH next_month_forecast AS (
    SELECT
        uf.section_id,
        ps.section_name,
        uf.forecast_month,
        uf.predicted_cpu_usage_pct,
        uf.predicted_memory_gb,
        uf.predicted_active_users
    FROM usage_forecasts uf
    JOIN platform_sections ps ON ps.section_id = uf.section_id
    WHERE uf.forecast_month = TO_CHAR(
        DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month', 'YYYY-MM'
    )
)
SELECT
    section_name,
    forecast_month,
    predicted_active_users,
    predicted_cpu_usage_pct,
    predicted_memory_gb,
    CASE
        WHEN predicted_cpu_usage_pct >= 85  THEN 'CRITICAL – scale up CPU immediately'
        WHEN predicted_cpu_usage_pct >= 70  THEN 'HIGH – plan CPU scaling this sprint'
        WHEN predicted_cpu_usage_pct >= 55  THEN 'MEDIUM – monitor closely'
        ELSE                                     'LOW – within normal bounds'
    END AS cpu_scaling_action,
    CASE
        WHEN predicted_memory_gb >= 450     THEN 'CRITICAL – memory near limit'
        WHEN predicted_memory_gb >= 380     THEN 'HIGH – increase memory allocation'
        WHEN predicted_memory_gb >= 300     THEN 'MEDIUM – review within 2 weeks'
        ELSE                                     'LOW – memory adequate'
    END AS memory_scaling_action
FROM next_month_forecast
ORDER BY predicted_cpu_usage_pct DESC;
