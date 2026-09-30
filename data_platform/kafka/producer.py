import hashlib
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class TelemetryEventSchema(BaseModel):
    """Telemetry schema enforcing strict resource bounds and HTTP status codes."""

    event_id: str
    service_name: str
    cpu_percent: float = Field(ge=0.0, le=100.0, description="CPU usage percent (0-100)")
    memory_percent: float = Field(ge=0.0, le=100.0, description="Memory usage percent (0-100)")
    latency_ms: float = Field(ge=0.0, description="Non-negative request latency in ms")
    status_code: int = Field(ge=100, le=599, description="Valid HTTP status code (100-599)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class DLQRecord(BaseModel):
    """Dead-letter queue payload capturing corrupt or non-conforming messages."""

    raw_payload: Any
    reason: str
    error_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TelemetryKafkaProducer:
    """Kafka Telemetry Producer with Pydantic validation, consistent hashing,

    and a Dead-Letter Queue (DLQ).
    """

    def __init__(self, num_partitions: int = 4):
        self.num_partitions = num_partitions
        self.partitions: dict[int, list[TelemetryEventSchema]] = {
            i: [] for i in range(num_partitions)
        }
        self.dlq: list[DLQRecord] = []

    def get_partition(self, service_name: str) -> int:
        """Determines target partition using deterministic consistent hashing."""
        digest = hashlib.md5(service_name.encode("utf-8")).hexdigest()
        return int(digest, 16) % self.num_partitions

    def produce(
        self, payload: dict[str, Any] | TelemetryEventSchema
    ) -> tuple[bool, str, int | None]:
        """Validates payload against schema and routes to partition or DLQ."""
        try:
            if isinstance(payload, TelemetryEventSchema):
                event = payload
            else:
                event = TelemetryEventSchema(**payload)

            partition = self.get_partition(event.service_name)
            self.partitions[partition].append(event)
            return True, f"Event accepted into partition {partition}", partition

        except (ValidationError, TypeError, ValueError) as err:
            reason = str(err)
            record = DLQRecord(
                raw_payload=payload,
                reason=reason,
                error_type=type(err).__name__,
            )
            self.dlq.append(record)
            return False, f"Event diverted to DLQ: {reason}", None

    def get_high_watermarks(self) -> dict[int, int]:
        """Returns total records produced per partition (high watermark)."""
        return {p: len(records) for p, records in self.partitions.items()}

    def get_partition_records(self, partition: int) -> list[TelemetryEventSchema]:
        """Fetches all records currently stored in a given partition."""
        return list(self.partitions.get(partition, []))

    def replay_dlq(self) -> list[tuple[bool, str, int | None]]:
        """Attempts to reprocess records stored in the Dead-Letter Queue."""
        replayed_results = []
        unresolved = []

        for record in self.dlq:
            if isinstance(record.raw_payload, dict):
                success, msg, part = self.produce(record.raw_payload)
                replayed_results.append((success, msg, part))
                if not success:
                    unresolved.append(record)
            else:
                replayed_results.append((False, "Non-dict payload cannot be auto-replayed", None))
                unresolved.append(record)

        self.dlq = unresolved
        return replayed_results
