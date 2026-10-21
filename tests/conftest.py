import pytest

from src.api.security import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate-limit counters are global; without a reset, tests that call the eval
    endpoints would start receiving 429s depending on test order."""
    limiter.reset()
    yield


@pytest.fixture(autouse=True)
def _scratch_data_dir(tmp_path, monkeypatch):
    """ETL / aggregation output goes to a temp dir, never to the tracked
    data/analytics/daily_service_metrics.parquet sample."""
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path / "data"))
