"""API key authentication and rate limiting for the /v1 API."""

import logging
import os
import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

API_KEY_ENV = "AEGIS_API_KEY"
API_KEY_HEADER = "X-API-Key"
PROTECTED_PREFIX = "/v1/"

# Shown as the "Authorize" button in /docs.
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def api_key_configured() -> bool:
    return bool(os.getenv(API_KEY_ENV, "").strip())


def require_api_key(request: Request, api_key: str | None = Security(api_key_header)) -> None:
    """Rejects /v1 requests without the configured key.

    /health, /metrics and the dashboard page stay open for probes, Prometheus and the
    browser. Without AEGIS_API_KEY (local development) every request is allowed; the
    production compose file and Helm chart refuse to start without one.
    """
    if not request.url.path.startswith(PROTECTED_PREFIX):
        return
    expected = os.getenv(API_KEY_ENV, "").strip()
    if not expected:
        return
    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )


# Evaluation and pipeline endpoints each take about a second of CPU, so a loop of
# calls could saturate every worker. Counters live in Redis when it is configured, so
# the limit applies across workers and pods instead of per process.
HEAVY_RATE_LIMIT = os.getenv("AEGIS_HEAVY_RATE_LIMIT", "10/minute")
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("AEGIS_REDIS_URL", "").strip() or "memory://",
)
