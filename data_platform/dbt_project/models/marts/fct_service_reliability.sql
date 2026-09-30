-- Mart model: fct_service_reliability
-- Aggregates MTTR, incident volume, and classifies services into reliability tiers

WITH staging AS (
    SELECT * FROM stg_incidents
),

aggregated AS (
    SELECT
        service_name,
        COUNT(ticket_id) AS total_incidents,
        SUM(CASE WHEN severity = 'P1' THEN 1 ELSE 0 END) AS p1_incident_count,
        SUM(CASE WHEN severity = 'P2' THEN 1 ELSE 0 END) AS p2_incident_count,
        ROUND(AVG(duration_minutes), 2) AS mttr_minutes,
        SUM(is_sla_breached) AS total_sla_breaches
    FROM staging
    GROUP BY service_name
)

SELECT
    service_name,
    total_incidents,
    p1_incident_count,
    p2_incident_count,
    mttr_minutes,
    total_sla_breaches,
    CASE
        WHEN total_sla_breaches = 0 AND mttr_minutes <= 15.0 THEN 'EXCELLENT'
        WHEN total_sla_breaches <= 1 AND mttr_minutes <= 60.0 THEN 'ACCEPTABLE'
        ELSE 'SLA_BREACH_RISK'
    END AS reliability_tier
FROM aggregated
