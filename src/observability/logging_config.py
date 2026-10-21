"""Structured JSON logging with a per-request correlation ID.

Log platforms (CloudWatch, Loki, ELK) index JSON fields, so one request can be
followed across every log line it produced by searching for its request_id.
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

LOG_FORMAT_ENV = "AEGIS_LOG_FORMAT"
LOG_LEVEL_ENV = "AEGIS_LOG_LEVEL"

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # An explicit extra={"request_id": ...} (the access log) wins over the context.
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    # Attributes every LogRecord has; anything else came from `extra=` and is emitted.
    _RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in self._RESERVED})
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """JSON logs when AEGIS_LOG_FORMAT=json (the Docker image default), text otherwise."""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if os.getenv(LOG_FORMAT_ENV, "text").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(os.getenv(LOG_LEVEL_ENV, "INFO").upper())
