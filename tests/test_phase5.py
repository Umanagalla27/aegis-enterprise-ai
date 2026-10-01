from fastapi.testclient import TestClient

from src.agents.rca_agent import RootCauseAnalysisAgent
from src.api.main import app
from src.observability.anomaly_engine import HybridAnomalyEngine
from src.observability.prometheus_exporter import get_prometheus_metrics


def test_anomaly_detection_zscore_and_isolation_forest():
    engine = HybridAnomalyEngine(z_threshold=3.0)

    # 1. Baseline normal events
    baseline = [
        {"cpu_percent": 30.0, "memory_percent": 40.0, "latency_ms": 45.0} for _ in range(50)
    ]
    engine.fit_baseline(baseline)

    # 2. Test normal event
    normal_res = engine.detect_zscore("latency_ms", 48.0)
    assert normal_res.is_anomaly is False
    assert normal_res.severity == "NORMAL"

    # 3. Test massive spike anomaly
    spike_res = engine.detect_zscore("latency_ms", 2500.0)
    assert spike_res.is_anomaly is True
    assert spike_res.severity == "CRITICAL"


def test_rca_agent_diagnosis_and_correlation():
    agent = RootCauseAnalysisAgent()

    anomaly_details = {"severity": "CRITICAL", "observed_value": 3200.0}
    logs = [
        {
            "service": "rag-retrieval",
            "level": "ERROR",
            "message": "Connection timeout to pgvector:5435",
        },
        {"service": "rag-retrieval", "level": "ERROR", "message": "Thread pool exhausted"},
    ]
    commits = [
        {
            "commit_hash": "a1b2c3d",
            "author": "sre-engineer",
            "message": "Update HNSW M parameter to 64",
            "service": "rag-retrieval",
        }
    ]

    report = agent.diagnose_incident(
        service_name="rag-retrieval",
        anomaly_details=anomaly_details,
        recent_logs=logs,
        recent_commits=commits,
    )

    assert report.severity == "P1"
    assert "a1b2c3d" in report.root_cause_summary
    assert len(report.correlated_logs) == 2
    assert "rag-retrieval" in report.blast_radius
    assert len(report.action_plan) >= 2


def test_fastapi_endpoints_and_prometheus_metrics():
    client = TestClient(app)

    # Health check
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "HEALTHY"

    # Ingest telemetry
    telemetry_payload = {
        "service_name": "api-gateway",
        "cpu_percent": 45.0,
        "memory_percent": 55.0,
        "latency_ms": 42.0,
        "status_code": 200,
    }
    t_res = client.post("/v1/telemetry/ingest", json=telemetry_payload)
    assert t_res.status_code == 200

    # Prometheus metrics endpoint
    m_res = client.get("/metrics")
    assert m_res.status_code == 200
    assert b"aegis_http_requests_total" in m_res.content

    # Direct prometheus exporter test
    metrics_data, content_type = get_prometheus_metrics()
    assert b"aegis_http_requests_total" in metrics_data
    assert "text/plain" in content_type
