import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RagasMetricScore:
    faithfulness: float
    answer_relevance: float
    context_precision: float
    context_recall: float
    passed_gate: bool


class EnterpriseRagasEvaluator:
    """
    RAGAS evaluation engine validating knowledge grounding and hallucination prevention.
    Strict enterprise thresholds:
      - Faithfulness >= 0.85
      - Context Recall >= 0.80
    """

    def __init__(
        self,
        min_faithfulness: float = 0.85,
        min_recall: float = 0.80,
    ):
        self.min_faithfulness = min_faithfulness
        self.min_recall = min_recall

    # Common words that carry no meaning for grounding checks.
    STOPWORDS = frozenset(
        "a an the is are was were be been of for to in on at by with and or "
        "what which when who how does do did this that it its as from must should can will".split()
    )

    @staticmethod
    def _stem(word: str) -> str:
        """Very small suffix stripper so "requires"/"require" and "alerts"/"alert" match."""
        for suffix in ("ing", "ed", "es", "s"):
            if len(word) > 4 and word.endswith(suffix):
                return word[: -len(suffix)]
        return word

    @classmethod
    def _content_words(cls, text: str) -> set[str]:
        words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
        return {cls._stem(w) for w in words if w not in cls.STOPWORDS}

    def evaluate_sample(
        self,
        query: str,
        retrieved_contexts: list[str],
        generated_answer: str,
        ground_truth: str,
    ) -> dict[str, float]:
        """Scores one query/answer pair with lexical-overlap proxies for the RAGAS metrics.

        These are word-overlap approximations, not the LLM-judged RAGAS library metrics.
        Scores are reported as computed. (An earlier version clamped them with
        max(0.85, ...), which made the gate impossible to fail.)
        """
        context_words = self._content_words(" ".join(retrieved_contexts))
        answer_words = self._content_words(generated_answer)
        truth_words = self._content_words(ground_truth)

        # Faithfulness: share of the answer's words that are supported by the context.
        faithfulness = len(answer_words & context_words) / max(1, len(answer_words))
        # Context recall: share of the ground truth that the retrieved context covers.
        context_recall = len(truth_words & context_words) / max(1, len(truth_words))
        # Answer relevance: share of the ground truth that the answer actually states.
        answer_relevance = len(answer_words & truth_words) / max(1, len(truth_words))
        # Context precision: share of retrieved contexts that contain ground-truth words.
        useful = sum(1 for c in retrieved_contexts if self._content_words(c) & truth_words)
        context_precision = useful / max(1, len(retrieved_contexts))

        return {
            "faithfulness": round(faithfulness, 3),
            "context_recall": round(context_recall, 3),
            "answer_relevance": round(answer_relevance, 3),
            "context_precision": round(context_precision, 3),
        }

    def evaluate_dataset(self, test_samples: list[dict[str, Any]]) -> RagasMetricScore:
        """Evaluates batch test dataset and verifies CI gate thresholds."""
        scores = [
            self.evaluate_sample(s["query"], s["contexts"], s["answer"], s["ground_truth"])
            for s in test_samples
        ]

        avg_faithfulness = round(sum(s["faithfulness"] for s in scores) / len(scores), 3)
        avg_recall = round(sum(s["context_recall"] for s in scores) / len(scores), 3)
        avg_relevance = round(sum(s["answer_relevance"] for s in scores) / len(scores), 3)
        avg_precision = round(sum(s["context_precision"] for s in scores) / len(scores), 3)

        passed = (avg_faithfulness >= self.min_faithfulness) and (avg_recall >= self.min_recall)

        return RagasMetricScore(
            faithfulness=avg_faithfulness,
            answer_relevance=avg_relevance,
            context_precision=avg_precision,
            context_recall=avg_recall,
            passed_gate=passed,
        )
