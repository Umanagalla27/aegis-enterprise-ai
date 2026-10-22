"""Concurrency stress test for PostgreSQL-backed LangGraph checkpointer.

Runs 20 create → approve HITL cycles across 2 worker threads.
All 20 must pass (resolve successfully) to validate multi-worker safety.

Each incident is started on one worker's graph and approved on the other's, the
case that returned 404 when paused incidents lived in process memory. Runs in CI
against the workflow's Postgres service container (AEGIS_TEST_DATABASE_URL).
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from langgraph.types import Command

from src.agents.checkpointing import build_checkpointer
from src.agents.graph import build_aegis_graph, thread_exists
from src.agents.state import IncidentTicket

TEST_DATABASE_URL = os.getenv("AEGIS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="AEGIS_TEST_DATABASE_URL not set")

NUM_RUNS = 20
NUM_WORKERS = 2


def _run_single_incident(run_index: int, start_app, resume_app) -> dict:
    """Start an incident on one worker's graph and approve it on the other's."""
    app = start_app
    thread_id = f"stress-{uuid.uuid4().hex[:8]}-{run_index}"
    config = {"configurable": {"thread_id": thread_id}}

    ticket = IncidentTicket(
        ticket_id=f"TKT-STRESS-{run_index}",
        service_name="rag-retrieval",
        description="CUDA Out of Memory crash detected in pod.",
    )

    state = {
        "ticket": ticket,
        "security_flagged": False,
        "triage": None,
        "kb_research": None,
        "rca_diagnosis": None,
        "actions": [],
        "review_status": "pending",
        "resolution_notes": None,
    }

    # Phase 1 — run until HITL pause
    for _ in app.stream(state, config=config):
        pass

    snapshot = app.get_state(config)
    assert len(snapshot.next) > 0, f"[run {run_index}] Graph should pause at HITL"

    # Verify thread is persisted in Postgres (not an in-memory set)
    assert thread_exists(resume_app, thread_id), (
        f"[run {run_index}] Thread {thread_id} not found in checkpointer"
    )

    # Phase 2 — resume with approval on the other worker
    app = resume_app
    for _ in app.stream(
        Command(resume={"approved": True, "reviewer": f"SRE_Worker_{run_index}"}),
        config=config,
    ):
        pass

    final = app.get_state(config).values
    return {
        "run_index": run_index,
        "thread_id": thread_id,
        "review_status": final["review_status"],
        "result": final["actions"][-1].result if final.get("actions") else None,
    }


def test_concurrent_postgres_checkpointer(monkeypatch):
    """20 create→approve cycles across 2 workers — all 20 must resolve."""
    monkeypatch.setenv("AEGIS_DATABASE_URL", TEST_DATABASE_URL)
    # One graph per simulated gunicorn worker / pod, each with its own pool
    workers = [build_aegis_graph(build_checkpointer()) for _ in range(NUM_WORKERS)]
    results = []
    errors = []

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
        futures = {
            pool.submit(
                _run_single_incident,
                i,
                workers[i % NUM_WORKERS],
                workers[(i + 1) % NUM_WORKERS],
            ): i
            for i in range(NUM_RUNS)
        }
        for future in as_completed(futures):
            run_idx = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                errors.append({"run_index": run_idx, "error": str(exc)})

    # Report
    passed = [r for r in results if r["review_status"] == "resolved"]
    failed = [r for r in results if r["review_status"] != "resolved"]

    print(f"\n{'=' * 60}")
    print("  Postgres Checkpointer Concurrency Test Results")
    print(f"  Workers: {NUM_WORKERS}  |  Total Runs: {NUM_RUNS}")
    print(f"  Passed: {len(passed)}  |  Failed: {len(failed)}  |  Errors: {len(errors)}")
    print(f"{'=' * 60}")

    for e in errors:
        print(f"  ERROR run {e['run_index']}: {e['error']}")
    for f in failed:
        print(f"  FAILED run {f['run_index']}: status={f['review_status']}")

    assert len(errors) == 0, f"{len(errors)} runs raised exceptions: {errors}"
    assert len(passed) == NUM_RUNS, (
        f"Only {len(passed)}/{NUM_RUNS} resolved. Failed: {failed}, Errors: {errors}"
    )
