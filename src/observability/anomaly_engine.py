import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)


@dataclass
class AnomalyResult:
    is_anomaly: bool
    confidence: float
    detector_type: str  # "Z_SCORE" or "ISOLATION_FOREST"
    severity: str  # "NORMAL", "WARNING", "CRITICAL"
    metric_name: str
    observed_value: float
    baseline_mean: float
    details: dict[str, Any]


class HybridAnomalyEngine:
    """
    Dual-layer anomaly detector:
    1. Rolling Z-Score for real-time univariate latency spike detection.
    2. Isolation Forest for multivariate anomaly detection across CPU, Memory, and Latency.
    """

    def __init__(self, z_threshold: float = 3.0, contamination: float = 0.05):
        self.z_threshold = z_threshold
        self.contamination = contamination
        self.isolation_forest = IsolationForest(
            contamination=contamination, random_state=42, n_estimators=100
        )
        self.is_fitted = False
        self.baseline_stats: dict[str, dict[str, float]] = {}

    def fit_baseline(self, historical_events: list[dict[str, Any]]) -> None:
        """Fits baseline mean/std and trains Isolation Forest on normal operational telemetry."""
        if not historical_events:
            return

        latencies = [e["latency_ms"] for e in historical_events]
        cpus = [e["cpu_percent"] for e in historical_events]
        mems = [e["memory_percent"] for e in historical_events]

        self.baseline_stats = {
            "latency_ms": {
                "mean": float(np.mean(latencies)),
                "std": float(np.std(latencies)) or 1.0,
            },
            "cpu_percent": {
                "mean": float(np.mean(cpus)),
                "std": float(np.std(cpus)) or 1.0,
            },
            "memory_percent": {
                "mean": float(np.mean(mems)),
                "std": float(np.std(mems)) or 1.0,
            },
        }

        # Fit multivariate Isolation Forest
        feature_matrix = np.array(
            [[e["cpu_percent"], e["memory_percent"], e["latency_ms"]] for e in historical_events]
        )
        self.isolation_forest.fit(feature_matrix)
        self.is_fitted = True
        logger.info("HybridAnomalyEngine fitted on %d baseline events.", len(historical_events))

    def detect_zscore(self, metric_name: str, value: float) -> AnomalyResult:
        """Fast statistical Z-score anomaly check."""
        stats = self.baseline_stats.get(metric_name, {"mean": value, "std": 1.0})
        std = stats.get("std", 1.0) or 1.0
        z = (value - stats["mean"]) / std

        is_anomaly = abs(z) > self.z_threshold
        severity = "NORMAL"
        if is_anomaly:
            severity = "CRITICAL" if abs(z) >= (self.z_threshold * 1.5) else "WARNING"

        return AnomalyResult(
            is_anomaly=is_anomaly,
            confidence=min(1.0, round(abs(z) / (self.z_threshold * 2), 2)),
            detector_type="Z_SCORE",
            severity=severity,
            metric_name=metric_name,
            observed_value=round(value, 2),
            baseline_mean=round(stats["mean"], 2),
            details={"z_score": round(z, 2), "threshold": self.z_threshold},
        )

    def detect_multivariate(self, event: dict[str, Any]) -> AnomalyResult:
        """Unsupervised multivariate anomaly detection."""
        if not self.is_fitted:
            # Fallback to univariate latency check if model not yet fitted
            return self.detect_zscore("latency_ms", event.get("latency_ms", 0.0))

        features = np.array([[event["cpu_percent"], event["memory_percent"], event["latency_ms"]]])
        pred = self.isolation_forest.predict(features)[0]  # -1 for anomaly, 1 for normal
        score = self.isolation_forest.score_samples(features)[0]

        is_anomaly = bool(pred == -1)
        severity = "NORMAL"
        if is_anomaly:
            severity = "CRITICAL" if score < -0.65 else "WARNING"

        return AnomalyResult(
            is_anomaly=is_anomaly,
            confidence=round(float(-score), 2),
            detector_type="ISOLATION_FOREST",
            severity=severity,
            metric_name="multivariate_telemetry",
            observed_value=event.get("latency_ms", 0.0),
            baseline_mean=self.baseline_stats.get("latency_ms", {}).get("mean", 0.0),
            details={"anomaly_score": round(float(score), 4)},
        )
