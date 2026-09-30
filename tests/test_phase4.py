from pathlib import Path

import pandas as pd
import pytest

from data_platform.airflow.dags.daily_sre_etl import (
    SLABreachException,
    evaluate_sla_gates,
    run_pipeline,
)
from data_platform.dbt_project.dbt_runner import DBTRunner
from data_platform.kafka.consumer import TelemetryKafkaConsumer
from data_platform.kafka.producer import TelemetryKafkaProducer
from data_platform.spark.batch_aggregator import SparkBatchAggregator


def test_kafka_producer_validation_and_dlq():
    producer = TelemetryKafkaProducer(num_partitions=4)

    # 1. Valid event
    valid_payload = {
        "event_id": "evt-valid-01",
        "service_name": "rag-retrieval",
        "cpu_percent": 45.0,
        "memory_percent": 60.5,
        "latency_ms": 32.4,
        "status_code": 200,
    }
    success, msg, partition = producer.produce(valid_payload)
    assert success is True
    assert partition is not None
    assert 0 <= partition < 4
    assert len(producer.dlq) == 0

    # Consistent hashing: same service always routes to same partition
    part2 = producer.get_partition("rag-retrieval")
    assert partition == part2

    # 2. Corrupt / invalid bounds -> diverted to DLQ
    invalid_cpu = {
        "event_id": "evt-invalid-01",
        "service_name": "rag-retrieval",
        "cpu_percent": 150.0,  # Invalid: > 100%
        "memory_percent": 50.0,
        "latency_ms": 10.0,
        "status_code": 200,
    }
    success_cpu, _, _ = producer.produce(invalid_cpu)
    assert success_cpu is False
    assert len(producer.dlq) == 1
    assert "cpu_percent" in producer.dlq[0].reason

    invalid_status = {
        "event_id": "evt-invalid-02",
        "service_name": "api-gateway",
        "cpu_percent": 20.0,
        "memory_percent": 30.0,
        "latency_ms": -5.0,  # Invalid: negative latency
        "status_code": 700,  # Invalid: > 599
    }
    success_status, _, _ = producer.produce(invalid_status)
    assert success_status is False
    assert len(producer.dlq) == 2


def test_kafka_consumer_lag_and_offsets():
    producer = TelemetryKafkaProducer(num_partitions=4)

    # Produce 10 events
    for i in range(10):
        producer.produce({
            "event_id": f"evt-{i}",
            "service_name": "api-gateway" if i % 2 == 0 else "rag-retrieval",
            "cpu_percent": 30.0,
            "memory_percent": 40.0,
            "latency_ms": 20.0 + i,
            "status_code": 200,
        })

    consumer = TelemetryKafkaConsumer(
        consumer_id="worker-01",
        group_id="telemetry-group",
        producer=producer,
    )

    # Initial lag before reading
    initial_lag = consumer.get_total_lag()
    assert initial_lag > 0
    assert consumer.verify_zero_lag() is False

    # Poll and commit offsets
    records = consumer.poll(max_records_per_partition=100)
    assert len(records) == initial_lag

    consumer.commit_offsets()
    assert consumer.get_total_lag() == 0
    assert consumer.verify_zero_lag() is True


def test_spark_batch_aggregator(tmp_path: Path):
    parquet_file = tmp_path / "test_metrics.parquet"
    aggregator = SparkBatchAggregator(output_path=parquet_file)

    sample_data = [
        {"service_name": "api-gateway", "cpu_percent": 20, "memory_percent": 30,
         "latency_ms": 10, "status_code": 200},
        {"service_name": "api-gateway", "cpu_percent": 25, "memory_percent": 35,
         "latency_ms": 50, "status_code": 200},
        {"service_name": "api-gateway", "cpu_percent": 30, "memory_percent": 40,
         "latency_ms": 100, "status_code": 500},
        {"service_name": "rag-retrieval", "cpu_percent": 70, "memory_percent": 80,
         "latency_ms": 200, "status_code": 200},
        {"service_name": "rag-retrieval", "cpu_percent": 75, "memory_percent": 85,
         "latency_ms": 300, "status_code": 200},
    ]

    summary_df, out_path = aggregator.run_daily_aggregation(sample_data)
    assert out_path.exists()

    # Read back parquet with pyarrow
    loaded_df = pd.read_parquet(out_path)
    assert len(loaded_df) == 2

    api_row = loaded_df[loaded_df["service_name"] == "api-gateway"].iloc[0]
    assert api_row["total_requests"] == 3
    assert api_row["total_errors_5xx"] == 1
    assert round(api_row["availability_sla"], 1) == 66.7
    assert api_row["latency_p50_ms"] <= api_row["latency_p95_ms"] <= api_row["latency_p99_ms"]


def test_dbt_models_and_runner():
    runner = DBTRunner(db_path=":memory:")

    incidents = [
        {
            "ticket_id": "TKT-P1-01",
            "service_name": "rag-retrieval",
            "severity": "P1",
            "started_at": "2026-09-30 10:00:00",
            "resolved_at": "2026-09-30 10:10:00",  # 10 min, target 15 min -> Met
        },
        {
            "ticket_id": "TKT-P2-01",
            "service_name": "rag-retrieval",
            "severity": "P2",
            "started_at": "2026-09-30 11:00:00",
            "resolved_at": "2026-09-30 12:30:00",  # 90 min, target 60 min -> Breached
        },
        {
            "ticket_id": "TKT-P3-01",
            "service_name": "api-gateway",
            "severity": "P3",
            "started_at": "2026-09-30 13:00:00",
            "resolved_at": "2026-09-30 14:00:00",  # 60 min, target 240 min -> Met
        },
    ]

    results = runner.run_pipeline(incidents)
    stg_df = results["stg_incidents"]
    marts_df = results["fct_service_reliability"]

    # Verify staging SLA breach calculation
    p1_row = stg_df[stg_df["ticket_id"] == "TKT-P1-01"].iloc[0]
    assert p1_row["sla_target_minutes"] == 15
    assert p1_row["is_sla_breached"] == 0

    p2_row = stg_df[stg_df["ticket_id"] == "TKT-P2-01"].iloc[0]
    assert p2_row["sla_target_minutes"] == 60
    assert p2_row["is_sla_breached"] == 1

    # Verify mart reliability tier classification
    api_mart = marts_df[marts_df["service_name"] == "api-gateway"].iloc[0]
    assert api_mart["total_sla_breaches"] == 0
    assert api_mart["reliability_tier"] in ("EXCELLENT", "ACCEPTABLE")

    runner.close()


def test_airflow_sla_gates():
    # 1. Healthy run passes gates
    healthy_avail = pd.DataFrame([
        {"service_name": "api-gateway", "availability_sla": 99.9},
        {"service_name": "rag-retrieval", "availability_sla": 99.5},
    ])
    healthy_marts = pd.DataFrame([
        {"service_name": "api-gateway", "mttr_minutes": 25.0},
        {"service_name": "rag-retrieval", "mttr_minutes": 40.0},
    ])
    result = evaluate_sla_gates(
        healthy_avail, healthy_marts, min_availability=99.0, max_mttr_minutes=60.0
    )
    assert result["status"] == "PASSED"

    # 2. Availability breach (< 99.0%) triggers gate failure
    unhealthy_avail = pd.DataFrame([
        {"service_name": "api-gateway", "availability_sla": 98.2},
    ])
    with pytest.raises(SLABreachException) as exc_avail:
        evaluate_sla_gates(
            unhealthy_avail, healthy_marts, min_availability=99.0, max_mttr_minutes=60.0
        )
    assert "Availability SLA Breach" in str(exc_avail.value)

    # 3. MTTR breach (> 60m) triggers gate failure
    unhealthy_marts = pd.DataFrame([
        {"service_name": "rag-retrieval", "mttr_minutes": 85.0},
    ])
    with pytest.raises(SLABreachException) as exc_mttr:
        evaluate_sla_gates(
            healthy_avail, unhealthy_marts, min_availability=99.0, max_mttr_minutes=60.0
        )
    assert "MTTR SLA Breach" in str(exc_mttr.value)

    # 4. End-to-end DAG pipeline execution
    pipeline_res = run_pipeline()
    assert pipeline_res["gate_evaluation"]["status"] == "PASSED"
    assert pipeline_res["publication"]["status"] == "PUBLISHED"
