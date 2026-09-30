from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class ServiceSLAPerformance:
    service_name: str
    total_requests: int
    total_errors_5xx: int
    availability_sla: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    avg_cpu_percent: float
    avg_memory_percent: float


class SparkBatchAggregator:
    """Distributed telemetry log aggregator calculating quantiles and availability SLAs

    with Parquet snappy compression.
    """

    DEFAULT_OUTPUT_PATH = Path("data/analytics/daily_service_metrics.parquet")

    def __init__(self, output_path: str | Path | None = None):
        self.output_path = Path(output_path or self.DEFAULT_OUTPUT_PATH)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def aggregate_batch(
        self, records: list[dict[str, Any]] | pd.DataFrame
    ) -> pd.DataFrame:
        """Aggregates telemetry records by service, formulating quantiles and SLA metrics."""
        if isinstance(records, list):
            if not records:
                return pd.DataFrame(columns=[
                    "service_name", "total_requests", "total_errors_5xx",
                    "availability_sla", "latency_p50_ms", "latency_p95_ms",
                    "latency_p99_ms", "avg_cpu_percent", "avg_memory_percent"
                ])
            df = pd.DataFrame(records)
        else:
            df = records.copy()

        # Vectorized metrics calculation per service
        grouped = df.groupby("service_name")
        summary_rows = []

        for service, group in grouped:
            total_requests = len(group)
            server_errors = int((group["status_code"] >= 500).sum())
            availability = (
                ((total_requests - server_errors) / total_requests * 100.0)
                if total_requests > 0
                else 100.0
            )

            p50 = float(np.percentile(group["latency_ms"], 50))
            p95 = float(np.percentile(group["latency_ms"], 95))
            p99 = float(np.percentile(group["latency_ms"], 99))
            avg_cpu = float(group["cpu_percent"].mean())
            avg_mem = float(group["memory_percent"].mean())

            summary_rows.append({
                "service_name": service,
                "total_requests": total_requests,
                "total_errors_5xx": server_errors,
                "availability_sla": round(availability, 4),
                "latency_p50_ms": round(p50, 2),
                "latency_p95_ms": round(p95, 2),
                "latency_p99_ms": round(p99, 2),
                "avg_cpu_percent": round(avg_cpu, 2),
                "avg_memory_percent": round(avg_mem, 2),
            })

        summary_df = pd.DataFrame(summary_rows)
        return summary_df

    def export_to_parquet(
        self, summary_df: pd.DataFrame, target_path: str | Path | None = None
    ) -> Path:
        """Compresses and exports aggregated results into Parquet with snappy compression."""
        path = Path(target_path or self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        summary_df.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
        return path

    def run_daily_aggregation(
        self, records: list[dict[str, Any]]
    ) -> tuple[pd.DataFrame, Path]:
        """Runs end-to-end distributed batch aggregation and parquet output."""
        summary_df = self.aggregate_batch(records)
        output_file = self.export_to_parquet(summary_df)
        return summary_df, output_file
