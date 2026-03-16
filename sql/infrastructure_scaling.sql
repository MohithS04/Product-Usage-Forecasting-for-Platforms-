-- =============================================================================
-- Infrastructure Scaling Needs Report
-- =============================================================================
-- Translates forecast data into actionable capacity-planning recommendations.
-- Results are stored in scaling_recommendations and can be exported to Tableau.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Generate Scaling Recommendations for the Next 3 Months
-- ---------------------------------------------------------------------------

INSERT INTO scaling_recommendations (
    section_id,
    recommendation_month,
    generated_date,
    current_capacity_units,
    recommended_capacity,
    scaling_direction,
    urgency_level,
    estimated_cost_impact,
    rationale,
    pm_summary
)
SELECT
    uf.section_id,
    uf.forecast_month                       AS recommendation_month,
    CURRENT_DATE                            AS generated_date,

    -- Current capacity baseline (assumed from last known actual)
    ROUND(mus.avg_cpu_usage_pct / 100.0 * 500)::INT  AS current_capacity_units,

    -- Recommended capacity: forecast CPU demand + 20% headroom
    ROUND(uf.predicted_cpu_usage_pct / 100.0 * 500 * 1.20)::INT AS recommended_capacity,

    -- Scaling direction
    CASE
        WHEN uf.predicted_cpu_usage_pct > mus.avg_cpu_usage_pct * 1.10 THEN 'scale_up'
        WHEN uf.predicted_cpu_usage_pct < mus.avg_cpu_usage_pct * 0.85 THEN 'scale_down'
        ELSE 'maintain'
    END AS scaling_direction,

    -- Urgency
    CASE
        WHEN uf.predicted_cpu_usage_pct >= 85 THEN 'critical'
        WHEN uf.predicted_cpu_usage_pct >= 70 THEN 'high'
        WHEN uf.predicted_cpu_usage_pct >= 55 THEN 'medium'
        ELSE 'low'
    END AS urgency_level,

    -- Rough cost impact (illustrative: $10 per capacity unit per month)
    ROUND((
        ROUND(uf.predicted_cpu_usage_pct / 100.0 * 500 * 1.20)
        - ROUND(mus.avg_cpu_usage_pct / 100.0 * 500)
    )::NUMERIC * 10.0, 2) AS estimated_cost_impact,

    -- Technical rationale
    FORMAT(
        'Forecast %s: predicted CPU %.1f%% vs current avg %.1f%%. ' ||
        'Predicted users: %s (current avg: %s). ' ||
        'Predicted memory: %.1f GB.',
        uf.forecast_month,
        uf.predicted_cpu_usage_pct,
        mus.avg_cpu_usage_pct,
        uf.predicted_active_users::BIGINT,
        mus.avg_active_users::BIGINT,
        uf.predicted_memory_gb
    ) AS rationale,

    -- Plain-language PM summary
    FORMAT(
        'For %s, the %s platform section is expected to have %s active users — ' ||
        '%s compared to last month. ' ||
        'Infrastructure load is forecast at %.0f%% CPU. ' ||
        'Recommended action: %s.',
        uf.forecast_month,
        ps.section_name,
        uf.predicted_active_users::BIGINT,
        CASE
            WHEN uf.predicted_active_users > mus.avg_active_users * 1.05
                THEN 'an increase of ' || ROUND((uf.predicted_active_users / NULLIF(mus.avg_active_users,0) - 1) * 100, 1)::TEXT || '%'
            WHEN uf.predicted_active_users < mus.avg_active_users * 0.95
                THEN 'a decrease of ' || ROUND((1 - uf.predicted_active_users / NULLIF(mus.avg_active_users,0)) * 100, 1)::TEXT || '%'
            ELSE 'roughly steady'
        END,
        uf.predicted_cpu_usage_pct,
        CASE
            WHEN uf.predicted_cpu_usage_pct >= 85 THEN 'Immediate scale-up required – risk of degraded service'
            WHEN uf.predicted_cpu_usage_pct >= 70 THEN 'Plan capacity increase within the next sprint'
            WHEN uf.predicted_cpu_usage_pct >= 55 THEN 'Monitor closely; no immediate action required'
            ELSE 'No scaling needed; capacity is comfortable'
        END
    ) AS pm_summary

FROM usage_forecasts uf
JOIN platform_sections ps ON ps.section_id = uf.section_id
JOIN LATERAL (
    -- Fetch the most recent actual monthly summary for context
    SELECT avg_cpu_usage_pct, avg_active_users, avg_memory_usage_gb
    FROM monthly_usage_summary
    WHERE section_id = uf.section_id
    ORDER BY year_month DESC
    LIMIT 1
) mus ON true
WHERE uf.forecast_run_date = (
    SELECT MAX(forecast_run_date) FROM usage_forecasts WHERE section_id = uf.section_id
)
ON CONFLICT (section_id, recommendation_month, generated_date) DO UPDATE
    SET recommended_capacity  = EXCLUDED.recommended_capacity,
        scaling_direction     = EXCLUDED.scaling_direction,
        urgency_level         = EXCLUDED.urgency_level,
        estimated_cost_impact = EXCLUDED.estimated_cost_impact,
        rationale             = EXCLUDED.rationale,
        pm_summary            = EXCLUDED.pm_summary,
        created_at            = CURRENT_TIMESTAMP;


-- ---------------------------------------------------------------------------
-- 2. Scaling Dashboard View (Tableau Data Source)
-- ---------------------------------------------------------------------------

SELECT
    ps.section_name,
    sr.recommendation_month,
    sr.scaling_direction,
    sr.urgency_level,
    sr.current_capacity_units,
    sr.recommended_capacity,
    (sr.recommended_capacity - sr.current_capacity_units) AS capacity_delta,
    sr.estimated_cost_impact,
    sr.pm_summary
FROM scaling_recommendations sr
JOIN platform_sections ps ON ps.section_id = sr.section_id
WHERE sr.generated_date = (
    SELECT MAX(generated_date) FROM scaling_recommendations
)
ORDER BY
    CASE sr.urgency_level
        WHEN 'critical' THEN 1
        WHEN 'high'     THEN 2
        WHEN 'medium'   THEN 3
        ELSE                 4
    END,
    ps.section_name;


-- ---------------------------------------------------------------------------
-- 3. Cost-Impact Summary by Section (next 3 months combined)
-- ---------------------------------------------------------------------------

SELECT
    ps.section_name,
    COUNT(*)                             AS forecast_months,
    SUM(sr.estimated_cost_impact)        AS total_cost_impact_usd,
    ROUND(AVG(sr.estimated_cost_impact), 2) AS avg_monthly_cost_impact,
    MAX(sr.urgency_level)                AS highest_urgency
FROM scaling_recommendations sr
JOIN platform_sections ps ON ps.section_id = sr.section_id
WHERE sr.generated_date = (
    SELECT MAX(generated_date) FROM scaling_recommendations
)
GROUP BY ps.section_name, sr.section_id
ORDER BY total_cost_impact_usd DESC;
