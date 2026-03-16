-- Extract historical usage data for forecasting
-- Aggregates daily metrics into monthly summaries per platform section

SELECT
    ps.section_name,
    strftime('%Y-%m', um.metric_date) AS usage_month,
    SUM(um.active_users)              AS total_active_users,
    SUM(um.api_calls)                 AS total_api_calls,
    SUM(um.ci_minutes)                AS total_ci_minutes,
    SUM(um.storage_gb)                AS total_storage_gb,
    SUM(um.compute_hours)             AS total_compute_hours,
    COUNT(DISTINCT um.metric_date)    AS days_in_period
FROM usage_metrics um
JOIN platform_sections ps ON ps.section_id = um.section_id
WHERE um.metric_date >= date('now', '-24 months')
GROUP BY ps.section_name, strftime('%Y-%m', um.metric_date)
ORDER BY ps.section_name, usage_month;
