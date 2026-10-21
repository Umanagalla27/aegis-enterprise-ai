"""API key authentication and rate limiting on the /v1 API."""

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.security import HEAVY_RATE_LIMIT

client = TestClient(app)
SEARCH = {"query": "GPU out of memory", "top_k": 1}


def test_v1_requires_key_when_configured(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "s3cret")

    assert client.post("/v1/rag/search", json=SEARCH).status_code == 401
    wrong = client.post("/v1/rag/search", json=SEARCH, headers={"X-API-Key": "nope"})
    assert wrong.status_code == 401
    ok = client.post("/v1/rag/search", json=SEARCH, headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200


def test_probes_metrics_and_dashboard_stay_open(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "s3cret")

    for path in ("/health", "/metrics", "/"):
        assert client.get(path).status_code == 200, path


def test_hitl_decision_cannot_be_forged_without_key(monkeypatch):
    monkeypatch.setenv("AEGIS_API_KEY", "s3cret")

    res = client.post(
        "/v1/agent/incidents/any-thread/decision",
        json={"approved": True, "reviewer": "attacker"},
    )
    assert res.status_code == 401


def test_open_when_no_key_configured(monkeypatch):
    monkeypatch.delenv("AEGIS_API_KEY", raising=False)

    assert client.post("/v1/rag/search", json=SEARCH).status_code == 200


def test_heavy_endpoints_are_rate_limited():
    allowed = int(HEAVY_RATE_LIMIT.split("/")[0])
    codes = [client.post("/v1/eval/ragas").status_code for _ in range(allowed + 1)]

    assert codes[:allowed] == [200] * allowed
    assert codes[-1] == 429
