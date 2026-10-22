import logging
import math
import os
import socket
import time
import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from langgraph.types import Command
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from eval.agent_evaluator import MultiAgentBenchmarkEvaluator
from eval.ragas_evaluator import EnterpriseRagasEvaluator
from eval.run_aiops_eval import evaluate_chaos
from src.agents.checkpointing import build_checkpointer
from src.agents.graph import build_aegis_graph, thread_exists
from src.agents.rca_agent import RootCauseAnalysisAgent
from src.agents.state import IncidentTicket
from src.api.dashboard import get_dashboard_html
from src.api.security import (
    HEAVY_RATE_LIMIT,
    api_key_configured,
    limiter,
    require_api_key,
)
from src.mcp.server import graph_rag, retriever
from src.observability.anomaly_engine import HybridAnomalyEngine
from src.observability.baseline_store import build_baseline_store
from src.observability.logging_config import configure_logging, request_id_var
from src.observability.otel_instrumentation import setup_tracing
from src.observability.prometheus_exporter import (
    ANOMALY_DETECTIONS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    get_prometheus_metrics,
)
from src.security.injection_defense import InjectionDefenseEngine
from src.security.pii_redactor import EnterprisePIIRedactor

configure_logging()
logger = logging.getLogger(__name__)
access_logger = logging.getLogger("aegis.access")

app = FastAPI(
    title="Aegis Enterprise AI Platform",
    version="1.0.0",
    description="Unified Enterprise GenAI & AIOps Platform",
    # Every /v1 route requires X-API-Key once AEGIS_API_KEY is set.
    dependencies=[Depends(require_api_key)],
)
app.state.limiter = limiter
setup_tracing(app)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 with the bad input echoed as text: the default handler echoed a JSON 1e309 as
    inf, which cannot be encoded, so the validation error itself became a 500."""
    detail = _json_safe(jsonable_encoder(exc.errors()))
    return JSONResponse(status_code=422, content={"detail": detail})


if not api_key_configured():
    logger.warning("AEGIS_API_KEY is not set: /v1 endpoints accept unauthenticated calls.")

# CORS: explicit origins from the environment instead of "*" combined with
# allow_credentials=True, which lets any website make credentialed calls.
_cors_origins = os.getenv("AEGIS_CORS_ORIGINS", "http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

rca_agent = RootCauseAnalysisAgent()

# Rolling per-service telemetry baselines. The engine used to be created with no
# baseline, so every Z-score was 0 and /v1/telemetry/ingest could never flag anything.
TELEMETRY_WARMUP_EVENTS = 20
TELEMETRY_WINDOW = 500
# Shared through Redis when AEGIS_REDIS_URL is set, so every worker and pod scores
# against the same baseline and it survives restarts.
baseline_store = build_baseline_store(TELEMETRY_WINDOW)

# Paused incidents live in the checkpointer (Postgres when AEGIS_DATABASE_URL is set).
# Keeping them in process memory made approvals fail with 404 whenever the decision
# request reached a different gunicorn worker or pod than the one that started it.
agent_app = build_aegis_graph(build_checkpointer())

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
    # Reuse the caller's / ingress's X-Request-ID so one ID follows the request across
    # services; every log line written while handling it carries the same ID.
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(request_id)
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    duration = time.perf_counter() - start_time
    response.headers["X-Request-ID"] = request_id

    # Label by the route template ("/v1/agent/incidents/{thread_id}"), not the raw URL.
    # Raw paths create one time series per incident id (unbounded label cardinality).
    route = request.scope.get("route")
    endpoint = getattr(route, "path", "unmatched")

    HTTP_REQUESTS_TOTAL.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=response.status_code,
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        endpoint=endpoint,
    ).observe(duration)

    if endpoint not in ("/health", "/metrics"):  # probes and scrapes would drown the log
        access_logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": endpoint,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
    return response


def _is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    """Helper to check if a local service port is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


# Bounds keep impossible readings out of the rolling baselines: one 1e309 (inf) used to
# poison a service's window, and every later ingest for it failed with a 500.
ServiceName = Annotated[str, Field(min_length=1, max_length=100)]
MAX_LATENCY_MS = 600_000


class TelemetryEvent(BaseModel):
    service_name: ServiceName
    cpu_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    memory_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    latency_ms: float = Field(ge=0, le=MAX_LATENCY_MS, allow_inf_nan=False)
    status_code: int = Field(ge=100, le=599)


class DiagnoseRequest(BaseModel):
    service_name: ServiceName
    observed_latency_ms: float = Field(ge=0, le=MAX_LATENCY_MS, allow_inf_nan=False)
    error_logs: list[dict] = Field(default=[], max_length=100)
    recent_commits: list[dict] = Field(default=[], max_length=100)


class AgentIncidentRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=4000)
    ticket_id: str | None = None


class AgentDecisionRequest(BaseModel):
    approved: bool
    reviewer: str = Field(min_length=1, max_length=100)


class RAGQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=2, ge=1, le=10)


class SecurityInspectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


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
    """Scores an event against that service's own recent history.

    The first TELEMETRY_WARMUP_EVENTS events per service only build the baseline.
    Anomalous events are not added to the window, so a spike cannot poison the baseline.
    """
    history = baseline_store.samples(event.service_name)
    sample = {
        "cpu_percent": event.cpu_percent,
        "memory_percent": event.memory_percent,
        "latency_ms": event.latency_ms,
    }

    if len(history) < TELEMETRY_WARMUP_EVENTS:
        baseline_events = baseline_store.append(event.service_name, sample)
        return {
            "service": event.service_name,
            "status": "WARMING_UP",
            "baseline_events": baseline_events,
            "events_needed": TELEMETRY_WARMUP_EVENTS,
            "anomaly_result": None,
        }

    engine = HybridAnomalyEngine()
    engine.fit_statistics(list(history))
    # Score every metric: a memory leak with normal latency used to go unnoticed.
    per_metric = {metric: engine.detect_zscore(metric, value) for metric, value in sample.items()}
    worst = max(per_metric.values(), key=lambda r: abs(r.details["z_score"]))
    if worst.is_anomaly:
        ANOMALY_DETECTIONS_TOTAL.labels(
            detector_type=worst.detector_type, severity=worst.severity
        ).inc()
        baseline_events = len(history)
    else:
        baseline_events = baseline_store.append(event.service_name, sample)
    return {
        "service": event.service_name,
        "status": "SCORED",
        "baseline_events": baseline_events,
        "anomaly_result": asdict(worst),
        "per_metric": {m: asdict(r) for m, r in per_metric.items()},
    }


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
            {"chunk_id": h.chunk_id, "text": h.text, "score": round(h.score, 4)} for h in hits
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
@limiter.limit(HEAVY_RATE_LIMIT)
def trigger_chaos_eval(request: Request):
    """Executes the 20-fault chaos benchmark plus 10 healthy controls."""
    summary = evaluate_chaos()
    return {
        "passed": summary.passed,
        "total_faults": summary.total_faults,
        "total_controls": summary.total_controls,
        "detection_rate": summary.detection_rate,
        "triage_accuracy": summary.triage_accuracy,
        "false_positive_rate": summary.false_positive_rate,
        "fault_types": ["LATENCY_SPIKE", "OOM_CRASH", "ERROR_BURST"],
        "cases": [asdict(c) for c in summary.cases],
    }


@app.post("/v1/eval/agents")
@limiter.limit(HEAVY_RATE_LIMIT)
def trigger_agent_eval(request: Request):
    """Runs the real LangGraph workflow over 50 labelled scenarios."""
    result = MultiAgentBenchmarkEvaluator().run_50_scenarios()
    misses = [asdict(o) for o in result.outcomes if not (o.correct and o.hitl_compliant)]
    return {
        "total_scenarios": result.total_scenarios,
        "routing_accuracy": result.tool_selection_accuracy,
        "trajectory_efficiency_pct": result.trajectory_efficiency_pct,
        "hitl_compliance_pct": result.hitl_approval_compliance,
        "passed_gate": result.passed_gate,
        "failed_scenarios": misses,
    }


@app.post("/v1/eval/ragas")
@limiter.limit(HEAVY_RATE_LIMIT)
def trigger_ragas_eval(request: Request):
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
    per_sample = [
        {
            "query": d["query"],
            **evaluator.evaluate_sample(d["query"], d["contexts"], d["answer"], d["ground_truth"]),
        }
        for d in dataset
    ]
    return {
        "per_sample": per_sample,
        "faithfulness": scores.faithfulness,
        "context_recall": scores.context_recall,
        "answer_relevance": scores.answer_relevance,
        "context_precision": scores.context_precision,
        "passed_gate": scores.passed_gate,
    }


@app.post("/v1/airflow/run-etl")
@limiter.limit(HEAVY_RATE_LIMIT)
def trigger_airflow_etl(request: Request):
    """Executes the complete Airflow SRE ETL pipeline with Spark and dbt marts."""
    from data_platform.airflow.dags.daily_sre_etl import SLABreachException, run_pipeline

    try:
        result = run_pipeline()
    except SLABreachException as breach:
        # A breached SLA is a valid pipeline outcome, not a server crash (was HTTP 500).
        return {"status": "SLA_BREACH", "violations": str(breach)}
    return {
        "status": "SUCCESS",
        "gate_evaluation": result["gate_evaluation"],
        "publication": result["publication"],
        "spark_summary": result["spark_metrics"].to_dict(orient="records"),
        "dbt_marts_summary": result["dbt_marts"].to_dict(orient="records"),
    }


@app.post("/v1/spark/aggregate")
@limiter.limit(HEAVY_RATE_LIMIT)
def trigger_spark_aggregation(request: Request):
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


# ---------------------------------------------------------------------------
# LangGraph multi-agent workflow with Human-in-the-Loop approval
# ---------------------------------------------------------------------------


def _require_known_thread(thread_id: str) -> None:
    """404 unless the checkpointer holds state for this incident thread."""
    if not thread_exists(agent_app, thread_id):
        raise HTTPException(status_code=404, detail="Unknown incident thread")


def _agent_view(thread_id: str) -> dict:
    """Serialises the current LangGraph state for one incident thread."""
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = agent_app.get_state(config)
    values = snapshot.values
    pending = [intr.value for task in snapshot.tasks for intr in getattr(task, "interrupts", ())]
    triage = values.get("triage")
    return {
        "thread_id": thread_id,
        "status": "AWAITING_APPROVAL" if snapshot.next else "COMPLETED",
        "next_nodes": list(snapshot.next),
        "pending_approval": pending[0] if pending else None,
        "ticket": values["ticket"].model_dump() if values.get("ticket") else None,
        "security_flagged": values.get("security_flagged"),
        "triage": triage.model_dump() if triage else None,
        "kb_research": values.get("kb_research"),
        "rca_diagnosis": values.get("rca_diagnosis"),
        "actions": [a.model_dump() for a in values.get("actions", [])],
        "review_status": values.get("review_status"),
        "resolution_notes": values.get("resolution_notes"),
    }


@app.post("/v1/agent/incidents")
@limiter.limit(HEAVY_RATE_LIMIT)
def start_agent_incident(request: Request, req: AgentIncidentRequest):
    """Runs security -> triage -> research -> RCA -> planning.

    P1/P2 incidents pause before any rollback and wait for a human decision.
    """
    thread_id = f"inc-{uuid.uuid4().hex[:12]}"
    ticket = IncidentTicket(
        ticket_id=req.ticket_id or thread_id.upper(),
        service_name=req.service_name,
        description=req.description,
    )
    state = {
        "ticket": ticket,
        "security_flagged": False,
        "triage": None,
        "kb_research": None,
        "rca_diagnosis": None,
        "actions": [],
        "review_status": "pending",
        "resolution_notes": None,
    }
    config = {"configurable": {"thread_id": thread_id}}
    for _ in agent_app.stream(state, config=config):
        pass
    return _agent_view(thread_id)


@app.get("/v1/agent/incidents/{thread_id}")
def get_agent_incident(thread_id: str):
    _require_known_thread(thread_id)
    return _agent_view(thread_id)


@app.post("/v1/agent/incidents/{thread_id}/decision")
def decide_agent_incident(thread_id: str, req: AgentDecisionRequest):
    """Resumes a paused incident with the reviewer's approve/reject decision."""
    _require_known_thread(thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    if not agent_app.get_state(config).next:
        raise HTTPException(status_code=409, detail="Incident is not awaiting approval")
    decision = {"approved": req.approved, "reviewer": req.reviewer}
    for _ in agent_app.stream(Command(resume=decision), config=config):
        pass
    return _agent_view(thread_id)
