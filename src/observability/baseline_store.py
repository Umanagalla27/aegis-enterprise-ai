"""Per-service rolling telemetry windows used as anomaly baselines.

In-memory windows are private to one process: with several gunicorn workers or pods,
each learns its own baseline and loses it on restart. Redis shares one window per
service across all of them.
"""

import json
import logging
import os
from collections import defaultdict, deque
from typing import Protocol

logger = logging.getLogger(__name__)

REDIS_URL_ENV = "AEGIS_REDIS_URL"


class BaselineStore(Protocol):
    def samples(self, service: str) -> list[dict[str, float]]: ...

    def append(self, service: str, sample: dict[str, float]) -> int: ...


class InMemoryBaselineStore:
    def __init__(self, window: int):
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))

    def samples(self, service: str) -> list[dict[str, float]]:
        return list(self._history[service])

    def append(self, service: str, sample: dict[str, float]) -> int:
        history = self._history[service]
        history.append(sample)
        return len(history)


class RedisBaselineStore:
    """One capped Redis list per service, newest sample first."""

    KEY_PREFIX = "aegis:baseline:"

    def __init__(self, client, window: int):
        self._client = client
        self._window = window

    def samples(self, service: str) -> list[dict[str, float]]:
        raw = self._client.lrange(self.KEY_PREFIX + service, 0, self._window - 1)
        return [json.loads(item) for item in raw]

    def append(self, service: str, sample: dict[str, float]) -> int:
        key = self.KEY_PREFIX + service
        pipe = self._client.pipeline()
        pipe.lpush(key, json.dumps(sample))
        pipe.ltrim(key, 0, self._window - 1)
        pipe.llen(key)
        return int(pipe.execute()[-1])


def build_baseline_store(window: int) -> BaselineStore:
    """Returns a Redis-backed store when AEGIS_REDIS_URL is set, else an in-memory one."""
    redis_url = os.getenv(REDIS_URL_ENV, "").strip()
    if not redis_url:
        logger.warning(
            "%s is not set: telemetry baselines are kept per process and reset on restart.",
            REDIS_URL_ENV,
        )
        return InMemoryBaselineStore(window)

    import redis

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    client.ping()
    logger.info("Telemetry baselines are stored in Redis.")
    return RedisBaselineStore(client, window)
