-- Staging model: stg_incidents
-- Cleans raw incident logs, standardizes timestamps, calculates duration, and maps SLA targets

WITH source_data AS (
    SELECT
        ticket_id,
        service_name,
        UPPER(TRIM(severity)) AS severity,
        DATETIME(started_at) AS started_at,
        DATETIME(resolved_at) AS resolved_at
    FROM raw_incidents
    WHERE ticket_id IS NOT NULL
),

standardized AS (
    SELECT
        ticket_id,
        service_name,
        severity,
        started_at,
        resolved_at,
        ROUND((julianday(resolved_at) - julianday(started_at)) * 1440.0, 2) AS duration_minutes,
        CASE
            WHEN severity = 'P1' THEN 15
            WHEN severity = 'P2' THEN 60
            WHEN severity IN ('P3', 'P4') THEN 240
            ELSE 240
        END AS sla_target_minutes
    FROM source_data
)

SELECT
    ticket_id,
    service_name,
    severity,
    started_at,
    resolved_at,
    duration_minutes,
    sla_target_minutes,
    CASE
        WHEN duration_minutes > sla_target_minutes THEN 1
        ELSE 0
    END AS is_sla_breached
FROM standardized
