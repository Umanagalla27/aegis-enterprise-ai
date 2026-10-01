from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Metrics definitions
HTTP_REQUESTS_TOTAL = Counter(
    "aegis_http_requests_total",
    "Total HTTP requests handled by Aegis platform",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "aegis_http_request_duration_seconds",
    "HTTP request latency distribution in seconds",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

ACTIVE_INCIDENTS = Gauge(
    "aegis_active_incidents",
    "Number of currently open SRE incidents",
    ["service_name", "severity"],
)

ANOMALY_DETECTIONS_TOTAL = Counter(
    "aegis_anomaly_detections_total",
    "Total anomalies detected by AIOps engines",
    ["detector_type", "severity"],
)


def get_prometheus_metrics() -> tuple[bytes, str]:
    """Generates the latest Prometheus metrics in standard scrape format."""
    return generate_latest(), CONTENT_TYPE_LATEST
