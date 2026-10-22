"""Shared-state regression tests.

With several gunicorn workers or pods, state kept in process memory broke HITL
approvals (404 when the decision reached another worker), reset anomaly baselines on
restart, and reused incident IDs. The Postgres / Redis tests run in CI against the
workflow's service containers (AEGIS_TEST_DATABASE_URL / AEGIS_TEST_REDIS_URL).
"""

import os

import pytest
from langgraph.types import Command

from src.agents.graph import build_aegis_graph
from src.agents.rca_agent import RootCauseAnalysisAgent
from src.agents.state import IncidentTicket
from src.observability.baseline_store import InMemoryBaselineStore, RedisBaselineStore

TEST_DATABASE_URL = os.getenv("AEGIS_TEST_DATABASE_URL")
TEST_REDIS_URL = os.getenv("AEGIS_TEST_REDIS_URL")


def _initial_state(description: str) -> dict:
    return {
        "ticket": IncidentTicket(
            ticket_id="INC-TEST", service_name="rag-retrieval", description=description
        ),
        "security_flagged": False,
        "triage": None,
        "kb_research": None,
        "rca_diagnosis": None,
        "actions": [],
        "review_status": "pending",
        "resolution_notes": None,
    }


def test_incident_ids_are_unique_across_agent_instances():
    # Each gunicorn worker / pod builds its own agent; a per-process counter made
    # every one of them start at INC-0001.
    ids = {
        RootCauseAnalysisAgent().diagnose_incident("api-gateway", {}).incident_id for _ in range(50)
    }
    assert len(ids) == 50


def test_in_memory_baseline_store_caps_window():
    store = InMemoryBaselineStore(window=3)
    for i in range(5):
        count = store.append("svc", {"latency_ms": float(i)})
    assert count == 3
    assert [s["latency_ms"] for s in store.samples("svc")] == [2.0, 3.0, 4.0]


@pytest.mark.skipif(not TEST_REDIS_URL, reason="AEGIS_TEST_REDIS_URL not set")
def test_redis_baseline_store_is_shared_between_instances():
    import redis

    client = redis.Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    client.delete(RedisBaselineStore.KEY_PREFIX + "shared-svc")
    worker_a = RedisBaselineStore(client, window=3)
    worker_b = RedisBaselineStore(client, window=3)

    for i in range(5):
        worker_a.append("shared-svc", {"latency_ms": float(i)})

    # A second worker sees the same capped window (newest first).
    assert [s["latency_ms"] for s in worker_b.samples("shared-svc")] == [4.0, 3.0, 2.0]


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="AEGIS_TEST_DATABASE_URL not set")
def test_hitl_decision_can_be_resumed_by_another_worker(monkeypatch):
    from src.agents.checkpointing import build_checkpointer

    monkeypatch.setenv("AEGIS_DATABASE_URL", TEST_DATABASE_URL)
    # Two independently built graphs stand in for two gunicorn workers / pods.
    worker_a = build_aegis_graph(build_checkpointer())
    worker_b = build_aegis_graph(build_checkpointer())

    config = {"configurable": {"thread_id": "shared-state-test-thread"}}
    for _ in worker_a.stream(_initial_state("CUDA OOM critical"), config=config):
        pass
    assert worker_a.get_state(config).next  # paused for human approval

    paused = worker_b.get_state(config)
    assert paused.values, "worker B must see the incident worker A paused"
    for _ in worker_b.stream(Command(resume={"approved": True, "reviewer": "sre"}), config):
        pass

    final = worker_b.get_state(config)
    assert not final.next
    assert final.values["actions"][-1].status == "executed"


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="AEGIS_TEST_DATABASE_URL not set")
def test_concurrent_worker_startup_on_fresh_database_does_not_deadlock(monkeypatch):
    """Several workers creating the checkpoint schema at once used to crash
    (UniqueViolation) and, with a blocking advisory lock, deadlock against
    CREATE INDEX CONCURRENTLY so every worker hung until gunicorn killed it."""
    import threading
    import time
    import uuid

    import psycopg

    from src.agents.checkpointing import build_checkpointer

    schema = f"startup_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
    separator = "&" if "?" in TEST_DATABASE_URL else "?"
    monkeypatch.setenv(
        "AEGIS_DATABASE_URL", f"{TEST_DATABASE_URL}{separator}options=-csearch_path%3D{schema}"
    )

    errors: list[BaseException] = []

    def start_worker():
        try:
            build_checkpointer()
        except BaseException as exc:  # surfaced in the assertion below
            errors.append(exc)

    workers = [threading.Thread(target=start_worker, daemon=True) for _ in range(4)]
    try:
        for worker in workers:
            worker.start()
        deadline = time.monotonic() + 60
        for worker in workers:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))
        assert not any(w.is_alive() for w in workers), "worker startup deadlocked"
        assert not errors, errors
    finally:
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as admin:
            # Hung workers would block DROP SCHEMA; end their sessions first.
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE pid <> pg_backend_pid() AND datname = current_database()"
            )
            admin.execute(f"DROP SCHEMA {schema} CASCADE")
