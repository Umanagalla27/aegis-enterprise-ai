from eval.agent_evaluator import MultiAgentBenchmarkEvaluator
from eval.ragas_evaluator import EnterpriseRagasEvaluator


def test_ragas_evaluation_gate():
    """Build fails if Faithfulness < 0.85 or Context Recall < 0.80."""
    evaluator = EnterpriseRagasEvaluator(min_faithfulness=0.85, min_recall=0.80)
    dataset = [
        {
            "query": "What is the P1 incident SLA for db-writer deadlock?",
            "contexts": [
                "SRE SLA targets: P1 incidents require resolution within 15 minutes. "
                "db-writer connection pool timeouts are classified as P1."
            ],
            "answer": "The P1 incident SLA requires resolution within 15 minutes.",
            "ground_truth": "P1 incidents must be resolved within 15 minutes.",
        },
        {
            "query": "What is the threshold for Isolation Forest latency alert?",
            "contexts": [
                "Anomaly detection engine sets critical anomaly score threshold at -0.65 "
                "and Z-score threshold at 3.0."
            ],
            "answer": (
                "The anomaly detection engine triggers critical alerts when Z-score exceeds 3.0."
            ),
            "ground_truth": "Critical latency alert triggers when Z-score exceeds 3.0.",
        },
    ]

    result = evaluator.evaluate_dataset(dataset)
    assert result.passed_gate is True
    assert result.faithfulness >= 0.85
    assert result.context_recall >= 0.80


def test_multi_agent_50_scenarios_gate():
    """Build fails if agent tool accuracy < 90% or HITL compliance < 100%."""
    evaluator = MultiAgentBenchmarkEvaluator()
    result = evaluator.run_50_scenarios()

    assert result.passed_gate is True
    assert result.tool_selection_accuracy >= 0.90
    assert result.hitl_approval_compliance == 100.0
