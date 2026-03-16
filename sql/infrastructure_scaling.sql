-- Infrastructure Scaling Projection Query
-- Projects resource needs based on forecasted usage growth

SELECT
    ps.section_name,
    f.forecast_date,
    f.metric_name,
    f.predicted_value,
    f.upper_bound,
    CASE
        WHEN f.metric_name = 'compute_hours' AND f.upper_bound > 10000
            THEN 'Scale Up Required'
        WHEN f.metric_name = 'storage_gb' AND f.upper_bound > 5000
            THEN 'Storage Expansion Needed'
        WHEN f.metric_name = 'api_calls' AND f.upper_bound > 1000000
            THEN 'API Capacity Increase'
        ELSE 'Current Capacity Sufficient'
    END AS scaling_recommendation
FROM forecasts f
JOIN platform_sections ps ON ps.section_id = f.section_id
WHERE f.forecast_date BETWEEN date('now') AND date('now', '+6 months')
ORDER BY f.forecast_date, ps.section_name;
