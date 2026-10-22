"""Request correlation IDs and structured logs."""

import json
import logging

from fastapi.testclient import TestClient

from src.api.main import app
from src.observability.logging_config import JsonFormatter, RequestIdFilter, request_id_var

client = TestClient(app)


def test_request_id_is_propagated_or_generated():
    echoed = client.get("/health", headers={"X-Request-ID": "trace-me-123"})
    assert echoed.headers["X-Request-ID"] == "trace-me-123"

    generated = client.get("/health").headers["X-Request-ID"]
    assert len(generated) == 32


def test_json_log_lines_carry_request_id_and_extra_fields():
    record = logging.makeLogRecord(
        {"name": "aegis.access", "levelname": "INFO", "msg": "request", "status": 200}
    )
    token = request_id_var.set("req-42")
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)

    line = json.loads(JsonFormatter().format(record))
    assert line["request_id"] == "req-42"
    assert line["status"] == 200
    assert line["message"] == "request"
