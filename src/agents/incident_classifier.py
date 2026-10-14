"""Rule-based incident fault classifier shared by the LangGraph nodes and the RCA agent.

This is deliberately simple keyword matching (no LLM). Keeping it in one place means
triage, RCA and the evaluators all agree on what an "OOM" or "latency" incident is.
"""

import re
from typing import Literal

FaultType = Literal["OOM_CRASH", "LATENCY_SPIKE", "ERROR_BURST", "UNKNOWN"]

# Order matters: the first matching rule wins.
_FAULT_RULES: list[tuple[FaultType, re.Pattern[str]]] = [
    (
        "OOM_CRASH",
        re.compile(r"\b(oom|out of memory|oomkilled|memory leak|cuda)\b", re.IGNORECASE),
    ),
    (
        "LATENCY_SPIKE",
        re.compile(
            r"\b(timeout|timed out|high latency|latency spike|slow|p99|connection pool)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ERROR_BURST",
        re.compile(r"\b(5\d\d|error burst|exception|crashloop|regression)\b", re.IGNORECASE),
    ),
]

SEVERITY_BY_FAULT: dict[FaultType, Literal["P1", "P2", "P3"]] = {
    "OOM_CRASH": "P1",
    "ERROR_BURST": "P1",
    "LATENCY_SPIKE": "P2",
    "UNKNOWN": "P3",
}


def classify_fault(text: str) -> FaultType:
    """Returns the first fault type whose keywords appear in the text."""
    for fault, pattern in _FAULT_RULES:
        if pattern.search(text or ""):
            return fault
    return "UNKNOWN"
