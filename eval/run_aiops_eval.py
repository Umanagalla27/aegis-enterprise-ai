"""20-fault chaos evaluation for the anomaly engine + RCA agent.

What changed from the first version, and why:
  * Detection used to be `res.is_anomaly or status >= 500`, and every injected fault
    had status 500/503, so detection was 100% by construction. Detection now uses only
    the anomaly engine's signals.
  * The baseline was 80 identical events (std = 0, forced to 1.0), which made almost any
    value look anomalous. The baseline is now seeded random noise.
  * 10 healthy "control" events are included, so false positives are measured.
  * Triage accuracy now checks that the RCA agent picked the runbook for the injected
    fault type, not merely that some runbook was returned.
"""

import logging
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Ensure repository root is on sys.path when executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.rca_agent import RootCauseAnalysisAgent  # noqa: E402
from src.observability.anomaly_engine import HybridAnomalyEngine  # noqa: E402

logger = logging.getLogger(__name__)

DETECTION_GATE = 95.0
TRIAGE_GATE = 95.0
FALSE_POSITIVE_GATE = 10.0

# Telemetry signature and log line for each injected fault type.
FAULT_PROFILES = {
    "LATENCY_SPIKE": {
        "telemetry": {"cpu_percent": 48.0, "memory_percent": 52.0, "latency_ms": 2800.0},
        "log": "Upstream timeout after 2800ms waiting for connection pool",
        "commit": None,
    },
    "OOM_CRASH": {
        "telemetry": {"cpu_percent": 91.0, "memory_percent": 98.5, "latency_ms": 65.0},
        "log": "Container OOMKilled: CUDA out of memory while allocating batch",
        "commit": None,
    },
    "ERROR_BURST": {
        "telemetry": {"cpu_percent": 58.0, "memory_percent": 50.0, "latency_ms": 180.0},
        "log": "Unhandled exception: HTTP 503 returned to 37% of requests",
        "commit": {"commit_hash": "c8d9e0f", "author": "sre_lead", "message": "Canary build"},
    },
}

EXPECTED_RUNBOOK = RootCauseAnalysisAgent.RUNBOOKS


@dataclass
class ChaosCase:
    case_id: str
    kind: str  # fault type or "HEALTHY"
    telemetry: dict
    detected: bool
    detectors_fired: list[str]
    rca_fault_type: str | None
    rca_runbook: str | None
    triage_correct: bool | None


@dataclass
class ChaosSummary:
    total_faults: int
    total_controls: int
    detection_rate: float
    triage_accuracy: float
    false_positive_rate: float
    passed: bool
    cases: list[ChaosCase]


def _baseline(rng: random.Random, n: int = 200) -> list[dict]:
    return [
        {
            "cpu_percent": rng.gauss(30.0, 4.0),
            "memory_percent": rng.gauss(45.0, 3.0),
            "latency_ms": rng.gauss(42.0, 6.0),
        }
        for _ in range(n)
    ]


def _detect(engine: HybridAnomalyEngine, event: dict) -> list[str]:
    fired = []
    for metric in ("latency_ms", "cpu_percent", "memory_percent"):
        if engine.detect_zscore(metric, event[metric]).is_anomaly:
            fired.append(f"zscore:{metric}")
    if engine.detect_multivariate(event).is_anomaly:
        fired.append("isolation_forest")
    return fired


def evaluate_chaos(seed: int = 7) -> ChaosSummary:
    rng = random.Random(seed)
    engine = HybridAnomalyEngine()
    agent = RootCauseAnalysisAgent()
    engine.fit_baseline(_baseline(rng))

    fault_types = ["LATENCY_SPIKE", "OOM_CRASH", "ERROR_BURST"] * 6 + ["LATENCY_SPIKE", "OOM_CRASH"]
    cases: list[ChaosCase] = []

    for i, fault in enumerate(fault_types, 1):
        profile = FAULT_PROFILES[fault]
        # +/-5% jitter so every injected fault is slightly different.
        event = {k: v * rng.uniform(0.95, 1.05) for k, v in profile["telemetry"].items()}
        # Percentages cannot exceed 100 after jitter.
        event["cpu_percent"] = min(event["cpu_percent"], 100.0)
        event["memory_percent"] = min(event["memory_percent"], 100.0)
        fired = _detect(engine, event)

        commits = []
        if profile["commit"]:
            commits = [{**profile["commit"], "service": "rag-retrieval"}]
        report = agent.diagnose_incident(
            service_name="rag-retrieval",
            anomaly_details={"severity": "CRITICAL", "observed_value": event["latency_ms"]},
            recent_logs=[{"service": "rag-retrieval", "level": "ERROR", "message": profile["log"]}],
            recent_commits=commits,
        )
        cases.append(
            ChaosCase(
                case_id=f"FAULT-{i:02d}",
                kind=fault,
                telemetry={k: round(v, 1) for k, v in event.items()},
                detected=bool(fired),
                detectors_fired=fired,
                rca_fault_type=report.fault_type,
                rca_runbook=report.recommended_runbook,
                triage_correct=report.recommended_runbook == EXPECTED_RUNBOOK[fault],
            )
        )

    # Healthy controls drawn from the same distribution as the baseline.
    for j, event in enumerate(_baseline(rng, n=10), 1):
        fired = _detect(engine, event)
        cases.append(
            ChaosCase(
                case_id=f"CONTROL-{j:02d}",
                kind="HEALTHY",
                telemetry={k: round(v, 1) for k, v in event.items()},
                detected=bool(fired),
                detectors_fired=fired,
                rca_fault_type=None,
                rca_runbook=None,
                triage_correct=None,
            )
        )

    faults = [c for c in cases if c.kind != "HEALTHY"]
    controls = [c for c in cases if c.kind == "HEALTHY"]
    detection = sum(c.detected for c in faults) / len(faults) * 100
    triage = sum(bool(c.triage_correct) for c in faults) / len(faults) * 100
    false_pos = sum(c.detected for c in controls) / len(controls) * 100
    passed = (
        detection >= DETECTION_GATE and triage >= TRIAGE_GATE and false_pos <= FALSE_POSITIVE_GATE
    )

    return ChaosSummary(
        total_faults=len(faults),
        total_controls=len(controls),
        detection_rate=round(detection, 1),
        triage_accuracy=round(triage, 1),
        false_positive_rate=round(false_pos, 1),
        passed=passed,
        cases=cases,
    )


def run_chaos_benchmark() -> bool:
    summary = evaluate_chaos()
    print(
        f"\n[AIOps Chaos Eval] {summary.total_faults} injected faults + "
        f"{summary.total_controls} healthy controls"
    )
    print("=" * 80)
    print("CHAOS EVALUATION SUMMARY:")
    print(f"  Total Injected Faults:   {summary.total_faults}")
    print(f"  Fault Detection Rate:    {summary.detection_rate:.1f}%  (gate >= {DETECTION_GATE}%)")
    print(f"  RCA Triage Accuracy:     {summary.triage_accuracy:.1f}%  (gate >= {TRIAGE_GATE}%)")
    print(
        f"  False Positive Rate:     {summary.false_positive_rate:.1f}%  "
        f"(gate <= {FALSE_POSITIVE_GATE}%)"
    )
    print(f"  RESULT:                  {'PASSED' if summary.passed else 'FAILED'}")
    print("=" * 80 + "\n")
    return summary.passed


def summary_as_dict(summary: ChaosSummary) -> dict:
    return asdict(summary)


if __name__ == "__main__":
    # Exit non-zero on failure so the CI step actually fails the build.
    sys.exit(0 if run_chaos_benchmark() else 1)
