-- Automated Monthly Performance Variance Analysis
-- Compares actual usage against forecasted values for each section

SELECT
    ps.section_name,
    vr.report_month,
    vr.metric_name,
    vr.actual_value,
    vr.forecast_value,
    vr.variance_pct,
    CASE
        WHEN ABS(vr.variance_pct) <= 5.0  THEN 'On Track'
        WHEN ABS(vr.variance_pct) <= 10.0 THEN 'Minor Deviation'
        WHEN ABS(vr.variance_pct) <= 20.0 THEN 'Significant Deviation'
        ELSE 'Critical Deviation'
    END AS variance_status,
    CASE
        WHEN vr.variance_pct > 0 THEN 'Over Forecast'
        ELSE 'Under Forecast'
    END AS direction
FROM variance_reports vr
JOIN platform_sections ps ON ps.section_id = vr.section_id
WHERE vr.report_month = date('now', 'start of month', '-1 month')
ORDER BY ABS(vr.variance_pct) DESC;
