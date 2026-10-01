import logging
from typing import Any

logger = logging.getLogger(__name__)


class AegisMLflowTracker:
    """Lightweight MLflow experiment tracker for AIOps models and RAG evaluations."""

    def __init__(self, experiment_name: str = "aegis-aiops-evaluations"):
        self.experiment_name = experiment_name
        self.runs: dict[str, dict[str, Any]] = {}

    def log_run(
        self,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, float],
        tags: dict[str, str] | None = None,
    ) -> str:
        """Logs hyperparams, evaluation metrics, and run tags."""
        self.runs[run_name] = {
            "params": params,
            "metrics": metrics,
            "tags": tags or {},
        }
        logger.info(
            "Logged MLflow run '%s' | Metrics: %s",
            run_name,
            metrics,
        )
        return run_name

    def get_run(self, run_name: str) -> dict[str, Any]:
        return self.runs.get(run_name, {})
