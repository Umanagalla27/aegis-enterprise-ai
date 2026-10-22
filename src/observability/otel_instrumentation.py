"""Optional OpenTelemetry tracing for the FastAPI app.

Tracing is enabled only when OTEL_EXPORTER_OTLP_ENDPOINT points at a collector
(Jaeger, Tempo, an OpenTelemetry Collector, ...); otherwise nothing is exported.
"""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)

OTLP_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"


def setup_tracing(app: FastAPI, service_name: str = "aegis-api") -> bool:
    """Instruments every request with a span exported over OTLP/HTTP. Returns True if on."""
    if not os.getenv(OTLP_ENDPOINT_ENV, "").strip():
        return False

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    # The exporter reads the endpoint and headers from the standard OTEL_* variables.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
    logger.info("OpenTelemetry tracing enabled.")
    return True
