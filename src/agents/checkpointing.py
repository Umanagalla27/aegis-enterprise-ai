"""Checkpointer selection for the LangGraph incident workflow.

Paused HITL incidents must survive restarts and be visible to every worker and pod,
so production uses Postgres. Local development and unit tests fall back to memory.
"""

import logging
import os

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

DATABASE_URL_ENV = "AEGIS_DATABASE_URL"
# Arbitrary constant shared by all workers to serialise schema setup.
SETUP_LOCK_ID = 7_340_001


def build_checkpointer() -> BaseCheckpointSaver:
    """Returns a Postgres checkpointer when AEGIS_DATABASE_URL is set, else MemorySaver."""
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        logger.warning(
            "%s is not set: HITL incident state is kept in process memory. "
            "Run a single worker, or set %s for multi-worker / multi-pod deployments.",
            DATABASE_URL_ENV,
            DATABASE_URL_ENV,
        )
        return MemorySaver()

    # Imported lazily so local development does not need a Postgres driver.
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        database_url,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=True,
    )
    saver = PostgresSaver(pool)
    # Creates the checkpoint tables on first start; a no-op afterwards. Every worker and
    # pod starts at the same time, and concurrent CREATE TABLE statements collide
    # (UniqueViolation on pg_type), so setup runs under a cluster-wide advisory lock.
    with pool.connection() as lock_conn:
        lock_conn.execute("SELECT pg_advisory_lock(%s)", (SETUP_LOCK_ID,))
        try:
            saver.setup()
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(%s)", (SETUP_LOCK_ID,))
    logger.info("HITL incident state is stored in Postgres.")
    return saver
