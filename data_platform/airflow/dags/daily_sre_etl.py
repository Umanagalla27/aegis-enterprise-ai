from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd

from data_platform.dbt_project.dbt_runner import DBTRunner
from data_platform.spark.batch_aggregator import SparkBatchAggregator


class SLABreachException(Exception):
    """Raised when SRE availability or MTTR thresholds are violated."""


def extract_telemetry(raw_events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Task 1: Ingests raw telemetry events from Kafka or upstream sources."""
    if raw_events is not None:
        return raw_events

    # Default baseline sample if running standalone
    return [
        {
            "event_id": "evt-01",
            "service_name": "api-gateway",
            "cpu_percent": 35.0,
            "memory_percent": 42.0,
            "latency_ms": 14.2,
            "status_code": 200,
        },
        {
            "event_id": "evt-02",
            "service_name": "rag-retrieval",
            "cpu_percent": 78.5,
            "memory_percent": 82.1,
            "latency_ms": 120.4,
            "status_code": 200,
        },
    ]


def spark_batch_agg(
    telemetry_records: list[dict[str, Any]],
    output_path: str = "data/analytics/daily_service_metrics.parquet",
) -> pd.DataFrame:
    """Task 2: Distributed batch processing formulating quantiles and SLAs."""
    aggregator = SparkBatchAggregator(output_path=output_path)
    summary_df, _ = aggregator.run_daily_aggregation(telemetry_records)
    return summary_df


def dbt_run_models(incidents: list[dict[str, Any]] | None = None) -> dict[str, pd.DataFrame]:
    """Task 3: Executes dbt staging views and reliability marts."""
    runner = DBTRunner()
    try:
        sample_incidents = incidents or [
            {
                "ticket_id": "TKT-101",
                "service_name": "rag-retrieval",
                "severity": "P2",
                "started_at": "2026-09-30 10:00:00",
                "resolved_at": "2026-09-30 10:45:00",
            },
            {
                "ticket_id": "TKT-102",
                "service_name": "api-gateway",
                "severity": "P3",
                "started_at": "2026-09-30 11:00:00",
                "resolved_at": "2026-09-30 11:30:00",
            },
        ]
        return runner.run_pipeline(sample_incidents)
    finally:
        runner.close()


def evaluate_sla_gates(
    availability_df: pd.DataFrame,
    marts_df: pd.DataFrame,
    min_availability: float = 99.0,
    max_mttr_minutes: float = 60.0,
) -> dict[str, Any]:
    """Task 4: Evaluates SLA thresholds; breaches trigger task failure."""
    violations = []

    # 1. Evaluate Availability SLA gate
    for _, row in availability_df.iterrows():
        avail = float(row.get("availability_sla", 100.0))
        svc = row.get("service_name", "unknown")
        if avail < min_availability:
            violations.append(
                f"Availability SLA Breach on '{svc}': {avail:.2f}% < {min_availability:.2f}%"
            )

    # 2. Evaluate MTTR gate
    for _, row in marts_df.iterrows():
        mttr = float(row.get("mttr_minutes", 0.0))
        svc = row.get("service_name", "unknown")
        if mttr > max_mttr_minutes:
            violations.append(f"MTTR SLA Breach on '{svc}': {mttr:.1f}m > {max_mttr_minutes:.1f}m")

    if violations:
        error_msg = " | ".join(violations)
        raise SLABreachException(f"SLA Gates Failed: {error_msg}")

    return {
        "status": "PASSED",
        "min_availability_verified": min_availability,
        "max_mttr_verified": max_mttr_minutes,
        "evaluated_services_count": len(availability_df),
    }


def publish_metrics(gate_result: dict[str, Any]) -> dict[str, Any]:
    """Task 5: Publishes verified SRE reliability metrics to downstream consumers."""
    return {
        "status": "PUBLISHED",
        "gate_status": gate_result.get("status"),
        "published_at": datetime.now(UTC).isoformat(),
    }


def run_pipeline(
    raw_events: list[dict[str, Any]] | None = None,
    incidents: list[dict[str, Any]] | None = None,
    min_availability: float = 99.0,
    max_mttr_minutes: float = 60.0,
) -> dict[str, Any]:
    """Executes the full DAG pipeline sequence synchronously for standalone / CI runs."""
    # Pipeline: extract_telemetry -> spark_batch_agg -> dbt_run_models
    #           -> evaluate_sla_gates -> publish_metrics
    events = extract_telemetry(raw_events)
    spark_df = spark_batch_agg(events)
    dbt_results = dbt_run_models(incidents)
    marts_df = dbt_results["fct_service_reliability"]
    gate_eval = evaluate_sla_gates(
        availability_df=spark_df,
        marts_df=marts_df,
        min_availability=min_availability,
        max_mttr_minutes=max_mttr_minutes,
    )
    published = publish_metrics(gate_eval)

    return {
        "spark_metrics": spark_df,
        "dbt_marts": marts_df,
        "gate_evaluation": gate_eval,
        "publication": published,
    }


# Standalone Airflow DAG instantiation with graceful fallback
default_args = {
    "owner": "aegis_sre",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    dag = DAG(
        dag_id="daily_sre_etl",
        default_args=default_args,
        schedule_interval="@daily",
        catchup=False,
    )

    t1 = PythonOperator(task_id="extract_telemetry", python_callable=extract_telemetry, dag=dag)
    t2 = PythonOperator(task_id="spark_batch_agg", python_callable=spark_batch_agg, dag=dag)
    t3 = PythonOperator(task_id="dbt_run_models", python_callable=dbt_run_models, dag=dag)
    t4 = PythonOperator(task_id="evaluate_sla_gates", python_callable=evaluate_sla_gates, dag=dag)
    t5 = PythonOperator(task_id="publish_metrics", python_callable=publish_metrics, dag=dag)

    t1 >> t2 >> t3 >> t4 >> t5

except ImportError:
    # Standalone mock DAG for CI/environments without Apache Airflow installed
    class StandaloneDAG:
        dag_id = "daily_sre_etl"
        tasks = [
            "extract_telemetry",
            "spark_batch_agg",
            "dbt_run_models",
            "evaluate_sla_gates",
            "publish_metrics",
        ]
        run = staticmethod(run_pipeline)

    dag = StandaloneDAG()
