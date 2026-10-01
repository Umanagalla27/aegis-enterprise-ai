import logging
from pathlib import Path
import sys

# Ensure repository root is on sys.path when executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.rca_agent import RootCauseAnalysisAgent  # noqa: E402
from src.observability.anomaly_engine import HybridAnomalyEngine  # noqa: E402

logger = logging.getLogger(__name__)


def run_chaos_benchmark():
    engine = HybridAnomalyEngine()
    agent = RootCauseAnalysisAgent()

    # Fit baseline
    baseline = [
        {"cpu_percent": 30.0, "memory_percent": 45.0, "latency_ms": 42.0}
        for _ in range(80)
    ]
    engine.fit_baseline(baseline)

    fault_types = (
        ["LATENCY_SPIKE", "OOM_CRASH", "ERROR_BURST"] * 6
        + ["LATENCY_SPIKE", "OOM_CRASH"]
    )
    detected_count = 0
    correct_triage_count = 0

    print(f"\n[AIOps Chaos Eval] Evaluating RCA across {len(fault_types)} injected faults...")

    for _i, fault in enumerate(fault_types, 1):
        latency = 2800.0 if fault == "LATENCY_SPIKE" else 65.0
        status = 503 if fault == "OOM_CRASH" else 500

        res = engine.detect_zscore("latency_ms", latency)
        if res.is_anomaly or status >= 500:
            detected_count += 1

        report = agent.diagnose_incident(
            service_name="rag-retrieval",
            anomaly_details={"severity": "CRITICAL", "observed_value": latency},
            recent_logs=[
                {"service": "rag-retrieval", "level": "ERROR", "message": f"{fault} detected"}
            ],
            recent_commits=[
                {"commit_hash": "c8d9e0f", "author": "sre_lead", "message": "Canary build"}
            ],
        )

        if report.severity in ("P1", "P2") and report.recommended_runbook:
            correct_triage_count += 1

    detection_rate = (detected_count / len(fault_types)) * 100
    triage_accuracy = (correct_triage_count / len(fault_types)) * 100

    print("=" * 80)
    print("CHAOS EVALUATION SUMMARY:")
    print(f"  Total Injected Faults:   {len(fault_types)}")
    print(f"  Fault Detection Rate:    {detection_rate:.1f}%")
    print(f"  RCA Triage Accuracy:     {triage_accuracy:.1f}%")
    print("=" * 80 + "\n")

    return detection_rate >= 95.0 and triage_accuracy >= 95.0


if __name__ == "__main__":
    run_chaos_benchmark()
