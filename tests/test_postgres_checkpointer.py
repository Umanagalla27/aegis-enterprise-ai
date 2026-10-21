"""Concurrency stress test for PostgreSQL-backed LangGraph checkpointer.

Runs 20 create → approve HITL cycles across 2 worker threads.
All 20 must pass (resolve successfully) to validate multi-worker safety.

Requirements:
    - AEGIS_DATABASE_URL env var must be set
    - PostgreSQL must be reachable
"""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from langgraph.types import Command

from src.agents.graph import build_aegis_graph, thread_exists
from src.agents.state import IncidentTicket

# Skip the entire module if no database URL is configured
pytestmark = pytest.mark.skipif(
    not os.environ.get("AEGIS_DATABASE_URL"),
    reason="AEGIS_DATABASE_URL not set — skipping Postgres checkpointer tests",
)

NUM_RUNS = 20
NUM_WORKERS = 2


def _run_single_incident(run_index: int) -> dict:
    """Execute one full create → approve cycle and return the result."""
    app = build_aegis_graph()
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
    assert thread_exists(thread_id), (
        f"[run {run_index}] Thread {thread_id} not found in checkpointer"
    )

    # Phase 2 — resume with approval
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


def test_concurrent_postgres_checkpointer():
    """20 create→approve cycles across 2 workers — all 20 must resolve."""
    results = []
    errors = []

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as pool:
        futures = {pool.submit(_run_single_incident, i): i for i in range(NUM_RUNS)}
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
