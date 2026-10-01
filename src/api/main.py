import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from src.agents.rca_agent import RootCauseAnalysisAgent
from src.api.dashboard import get_dashboard_html
from src.observability.anomaly_engine import HybridAnomalyEngine
from src.observability.prometheus_exporter import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    get_prometheus_metrics,
)

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
