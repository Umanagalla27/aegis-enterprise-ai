import pytest

from src.api.security import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate-limit counters are global; without a reset, tests that call the eval
    endpoints would start receiving 429s depending on test order."""
    limiter.reset()
    yield
