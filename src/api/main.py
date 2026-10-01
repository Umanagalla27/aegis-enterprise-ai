import socket
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from eval.ragas_evaluator import EnterpriseRagasEvaluator
from eval.run_aiops_eval import run_chaos_benchmark
from src.agents.rca_agent import RootCauseAnalysisAgent
from src.api.dashboard import get_dashboard_html
from src.mcp.server import graph_rag, retriever
from src.observability.anomaly_engine import HybridAnomalyEngine
from src.observability.prometheus_exporter import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    get_prometheus_metrics,
)
from src.security.injection_defense import InjectionDefenseEngine
from src.security.presidio_redactor import EnterprisePIIRedactor

app = FastAPI(
    title="Aegis Enterprise AI Platform",
    version="1.0.0",
    description="Unified Enterprise GenAI & AIOps Platform",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

anomaly_engine = HybridAnomalyEngine()
rca_agent = RootCauseAnalysisAgent()

# Pre-populate RAG runbooks for instant interactive testing
if not retriever.documents:
    sample_docs = [
        {
            "chunk_id": "RUNBOOK-101",
            "text": (
                "Runbook 101: GPU CUDA Out of Memory (OOM) Mitigation. "
                "Reduce batch size to 32, enable flash-attention, and clear CUDA cache."
            ),
            "metadata": {"type": "runbook", "service": "rag-retrieval"},
        },
        {
            "chunk_id": "RUNBOOK-102",
            "text": (
                "Runbook 102: Database Connection Pool Exhaustion. Inspect active queries "
                "on pgvector:5435, flush Redis cache on :6382, and scale read replicas."
            ),
            "metadata": {"type": "runbook", "service": "aegis-postgres"},
        },
        {
            "chunk_id": "RUNBOOK-103",
            "text": (
                "Runbook 103: Canary Deployment Regression Rollback. Initiate git rollback "
                "to previous stable commit, drain unhealthy pods, and verify P99 latency."
            ),
            "metadata": {"type": "runbook", "service": "api-gateway"},
        },
    ]
    retriever.index_documents(sample_docs)


# OpenTelemetry & Prometheus Middleware
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    HTTP_REQUESTS_TOTAL.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        endpoint=request.url.path,
    ).observe(duration)

    return response


def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    """Helper to check if a local service port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


class TelemetryEvent(BaseModel):
    service_name: str
    cpu_percent: float
    memory_percent: float
    latency_ms: float
    status_code: int


class DiagnoseRequest(BaseModel):
    service_name: str
    observed_latency_ms: float
    error_logs: list[dict] = []
    recent_commits: list[dict] = []


class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 2


class SecurityInspectRequest(BaseModel):
    text: str


@app.get("/", response_class=HTMLResponse)
def index():
    """Serves the Aegis Enterprise AI interactive web control center."""
    return get_dashboard_html()


@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "version": "1.0.0"}


@app.get("/metrics")
def metrics():
    data, content_type = get_prometheus_metrics()
    return Response(content=data, media_type=content_type)


@app.get("/v1/services/status")
def get_services_status():
    """Returns real-time reachability status for all platform services."""
    services = {
        "fastapi": {"name": "Aegis FastAPI Backend", "port": 8000, "online": True},
        "prometheus": {
            "name": "Prometheus Metrics UI",
            "port": 9091,
            "online": _is_port_open("127.0.0.1", 9091),
        },
        "grafana": {
            "name": "Grafana Dashboards",
            "port": 3001,
            "online": _is_port_open("127.0.0.1", 3001),
        },
        "postgres": {
            "name": "PostgreSQL (pgvector)",
            "port": 5435,
            "online": _is_port_open("127.0.0.1", 5435),
        },
        "redis": {
            "name": "Redis 7 Cache",
            "port": 6382,
            "online": _is_port_open("127.0.0.1", 6382),
        },
        "mlflow": {
            "name": "MLflow Tracking Server",
            "port": 5000,
            "online": _is_port_open("127.0.0.1", 5000),
        },
        "airflow": {
            "name": "Airflow Webserver",
            "port": 8080,
            "online": _is_port_open("127.0.0.1", 8080),
        },
        "pyspark": {
            "name": "PySpark (Spark UI)",
            "port": 4040,
            "online": _is_port_open("127.0.0.1", 4040),
        },
        "helm": {
            "name": "Helm Chart & GitOps",
            "port": "ArgoCD",
            "online": True,
        },
    }
    return {"services": services}


@app.post("/v1/telemetry/ingest")
def ingest_telemetry(event: TelemetryEvent):
    res = anomaly_engine.detect_zscore("latency_ms", event.latency_ms)
    return {"service": event.service_name, "anomaly_result": res}


@app.post("/v1/incidents/diagnose")
def diagnose_incident(req: DiagnoseRequest):
    anomaly_details = {
        "severity": "CRITICAL" if req.observed_latency_ms > 1000 else "WARNING",
        "observed_value": req.observed_latency_ms,
    }
    report = rca_agent.diagnose_incident(
        service_name=req.service_name,
        anomaly_details=anomaly_details,
        recent_logs=req.error_logs,
        recent_commits=req.recent_commits,
    )
    return {"report": report}


@app.post("/v1/rag/search")
def search_rag(req: RAGQueryRequest):
    """Executes hybrid BM25 + dense retrieval across enterprise runbooks."""
    hits = retriever.search_hybrid(req.query, top_k=req.top_k)
    return {
        "query": req.query,
        "results": [
            {"chunk_id": h.chunk_id, "text": h.text, "score": round(h.score, 4)}
            for h in hits
        ],
    }


@app.post("/v1/rag/topology")
def get_topology(service_name: str):
    """Retrieves upstream dependencies and downstream blast radius for a service."""
    blast_radius = graph_rag.get_blast_radius(service_name)
    dependencies = graph_rag.get_dependencies(service_name)
    return {
        "service": service_name,
        "dependencies": dependencies,
        "blast_radius": blast_radius,
    }


@app.post("/v1/security/inspect")
def inspect_security(req: SecurityInspectRequest):
    """Evaluates prompt injection signatures and redacts sensitive PII."""
    is_attack, attack_reason = InjectionDefenseEngine.is_adversarial(req.text)
    redaction = EnterprisePIIRedactor.redact(req.text)
    return {
        "is_adversarial": is_attack,
        "attack_reason": attack_reason,
        "redacted_text": redaction.clean_text,
        "redacted_count": redaction.redacted_items_count,
        "detected_entities": redaction.detected_entities,
    }


@app.post("/v1/eval/chaos")
def trigger_chaos_eval():
    """Executes the 20-injected fault chaos evaluation benchmark."""
    passed = run_chaos_benchmark()
    return {
        "passed": passed,
        "total_faults": 20,
        "fault_types": ["LATENCY_SPIKE", "OOM_CRASH", "ERROR_BURST"],
    }


@app.post("/v1/eval/ragas")
def trigger_ragas_eval():
    """Runs enterprise RAGAS evaluation on reference query-context-ground truth samples."""
    evaluator = EnterpriseRagasEvaluator(min_faithfulness=0.85, min_recall=0.80)
    dataset = [
        {
            "query": "What is the P1 incident SLA for db-writer deadlock?",
            "contexts": [
                "SRE SLA targets: P1 incidents require resolution within 15 minutes. "
                "db-writer connection pool timeouts are classified as P1."
            ],
            "answer": "The P1 incident SLA requires resolution within 15 minutes.",
            "ground_truth": "P1 incidents must be resolved within 15 minutes.",
        },
        {
            "query": "What is the threshold for Isolation Forest latency alert?",
            "contexts": [
                "Anomaly detection engine sets critical anomaly score threshold at -0.65 "
                "and Z-score threshold at 3.0."
            ],
            "answer": (
                "The anomaly detection engine triggers critical alerts when Z-score exceeds 3.0."
            ),
            "ground_truth": "Critical latency alert triggers when Z-score exceeds 3.0.",
        },
    ]
    scores = evaluator.evaluate_dataset(dataset)
    return {
        "faithfulness": scores.faithfulness,
        "context_recall": scores.context_recall,
        "answer_relevance": scores.answer_relevance,
        "context_precision": scores.context_precision,
        "passed_gate": scores.passed_gate,
    }


@app.post("/v1/airflow/run-etl")
def trigger_airflow_etl():
    """Executes the complete Airflow SRE ETL pipeline with Spark and dbt marts."""
    from data_platform.airflow.dags.daily_sre_etl import run_pipeline

    result = run_pipeline()
    return {
        "status": "SUCCESS",
        "gate_evaluation": result["gate_evaluation"],
        "publication": result["publication"],
        "spark_summary": result["spark_metrics"].to_dict(orient="records"),
        "dbt_marts_summary": result["dbt_marts"].to_dict(orient="records"),
    }


@app.post("/v1/spark/aggregate")
def trigger_spark_aggregation():
    """Executes distributed telemetry log aggregation formulating quantiles & SLAs."""
    from data_platform.spark.batch_aggregator import SparkBatchAggregator

    aggregator = SparkBatchAggregator()
    sample_records = [
        {
            "service_name": "api-gateway",
            "status_code": 200,
            "latency_ms": 14.5,
            "cpu_percent": 34.0,
            "memory_percent": 41.0,
        },
        {
            "service_name": "api-gateway",
            "status_code": 200,
            "latency_ms": 18.2,
            "cpu_percent": 36.0,
            "memory_percent": 43.0,
        },
        {
            "service_name": "api-gateway",
            "status_code": 500,
            "latency_ms": 120.0,
            "cpu_percent": 45.0,
            "memory_percent": 48.0,
        },
        {
            "service_name": "rag-retrieval",
            "status_code": 200,
            "latency_ms": 95.0,
            "cpu_percent": 75.0,
            "memory_percent": 80.0,
        },
        {
            "service_name": "rag-retrieval",
            "status_code": 200,
            "latency_ms": 110.0,
            "cpu_percent": 82.0,
            "memory_percent": 84.0,
        },
        {
            "service_name": "rag-retrieval",
            "status_code": 503,
            "latency_ms": 2500.0,
            "cpu_percent": 95.0,
            "memory_percent": 91.0,
        },
    ]
    summary_df, _ = aggregator.run_daily_aggregation(sample_records)
    return {
        "status": "SUCCESS",
        "records_processed": len(sample_records),
        "aggregated_metrics": summary_df.to_dict(orient="records"),
    }

