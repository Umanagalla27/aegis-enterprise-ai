import pytest

from eval.agent_evaluator import MultiAgentBenchmarkEvaluator
from eval.ragas_evaluator import EnterpriseRagasEvaluator

GROUNDED_SAMPLE = {
    "query": "What is the P1 incident SLA for db-writer deadlock?",
    "contexts": [
        "SRE SLA targets: P1 incidents require resolution within 15 minutes. "
        "db-writer connection pool timeouts are classified as P1."
    ],
    "answer": "The P1 incident SLA requires resolution within 15 minutes.",
    "ground_truth": "P1 incidents must be resolved within 15 minutes.",
}

# The retrieved context only states the thresholds; it never says a *latency alert*
# fires when the Z-score is exceeded. Honest scoring flags the missing support.
UNDER_SUPPORTED_SAMPLE = {
    "query": "What is the threshold for Isolation Forest latency alert?",
    "contexts": [
        "Anomaly detection engine sets critical anomaly score threshold at -0.65 "
        "and Z-score threshold at 3.0."
    ],
    "answer": "The anomaly detection engine triggers critical alerts when Z-score exceeds 3.0.",
    "ground_truth": "Critical latency alert triggers when Z-score exceeds 3.0.",
}

HALLUCINATED_SAMPLE = {
    **GROUNDED_SAMPLE,
    "answer": "Bananas are yellow and the moon is made of cheese.",
}


def test_ragas_gate_passes_grounded_answer():
    """A fully supported answer must clear Faithfulness >= 0.85 and Recall >= 0.80."""
    evaluator = EnterpriseRagasEvaluator(min_faithfulness=0.85, min_recall=0.80)
    result = evaluator.evaluate_dataset([GROUNDED_SAMPLE])
    assert result.passed_gate is True
    assert result.faithfulness >= 0.85
    assert result.context_recall >= 0.80


def test_ragas_gate_rejects_hallucinated_answer():
    """Regression: scores used to be clamped to 0.85, so nonsense passed the gate."""
    evaluator = EnterpriseRagasEvaluator(min_faithfulness=0.85, min_recall=0.80)
    result = evaluator.evaluate_dataset([HALLUCINATED_SAMPLE])
    assert result.passed_gate is False
    assert result.faithfulness < 0.2


def test_ragas_gate_flags_context_missing_the_fact():
    evaluator = EnterpriseRagasEvaluator(min_faithfulness=0.85, min_recall=0.80)
    result = evaluator.evaluate_dataset([UNDER_SUPPORTED_SAMPLE])
    assert result.passed_gate is False
    assert result.context_recall < 0.80


def test_agent_never_rolls_back_without_approval():
    """Safety invariant: no scenario executes a rollback unless a human approved it."""
    result = MultiAgentBenchmarkEvaluator().run_50_scenarios()
    for o in result.outcomes:
        if o.rollback_executed:
            assert o.paused_for_human, f"{o.scenario_id} rolled back without a human decision"
        if o.expected_route in ("P3", "QUARANTINE"):
            assert not o.rollback_executed, f"{o.scenario_id} rolled back a {o.expected_route}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: keyword triage routes 'dashboard feels sluggish' to P3, so a P2 "
        "incident skips human review (HITL 90%). Fix the classifier, then remove this marker."
    ),
)
def test_multi_agent_scenarios_gate():
    """Runs the real LangGraph workflow on labelled scenarios.

    Gate: severity accuracy >= 90% and HITL compliance == 100%.
    """
    evaluator = MultiAgentBenchmarkEvaluator()
    result = evaluator.run_50_scenarios()

    assert result.total_scenarios == 50
    assert result.passed_gate is True
    assert result.tool_selection_accuracy >= 0.90
    assert result.hitl_approval_compliance == 100.0
