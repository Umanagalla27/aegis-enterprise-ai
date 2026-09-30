from typing import Any

from data_platform.kafka.producer import TelemetryEventSchema, TelemetryKafkaProducer


class ConsumerGroupManager:
    """Coordinates partition assignment across consumers in a consumer group."""

    def __init__(self, group_id: str, num_partitions: int = 4):
        self.group_id = group_id
        self.num_partitions = num_partitions
        self.members: list[str] = []

    def register_consumer(self, consumer_id: str) -> None:
        if consumer_id not in self.members:
            self.members.append(consumer_id)

    def unregister_consumer(self, consumer_id: str) -> None:
        if consumer_id in self.members:
            self.members.remove(consumer_id)

    def get_assigned_partitions(self, consumer_id: str) -> list[int]:
        """Distributes partitions evenly across active group members (Round-Robin)."""
        if consumer_id not in self.members:
            return []
        member_idx = self.members.index(consumer_id)
        total_members = len(self.members)

        return [
            p for p in range(self.num_partitions)
            if p % total_members == member_idx
        ]


class TelemetryKafkaConsumer:
    """Streaming consumer with offset management, consumer group partition assignment,

    and consumer lag monitoring.
    """

    def __init__(
        self,
        consumer_id: str,
        group_id: str,
        producer: TelemetryKafkaProducer,
        group_manager: ConsumerGroupManager | None = None,
    ):
        self.consumer_id = consumer_id
        self.group_id = group_id
        self.producer = producer
        self.group_manager = group_manager or ConsumerGroupManager(
            group_id=group_id, num_partitions=producer.num_partitions
        )
        self.group_manager.register_consumer(consumer_id)

        self.committed_offsets: dict[int, int] = {}
        self.current_offsets: dict[int, int] = {}

        for p in self.assigned_partitions:
            self.committed_offsets[p] = 0
            self.current_offsets[p] = 0

    @property
    def assigned_partitions(self) -> list[int]:
        return self.group_manager.get_assigned_partitions(self.consumer_id)

    def poll(self, max_records_per_partition: int = 100) -> list[TelemetryEventSchema]:
        """Polls records from all assigned partitions up to high watermark."""
        batch: list[TelemetryEventSchema] = []

        for p in self.assigned_partitions:
            records = self.producer.get_partition_records(p)
            current = self.current_offsets.get(p, 0)
            available = records[current : current + max_records_per_partition]
            batch.extend(available)
            self.current_offsets[p] = current + len(available)

        return batch

    def commit_offsets(self) -> None:
        """Commits current read positions per partition."""
        for p in self.assigned_partitions:
            self.committed_offsets[p] = self.current_offsets.get(p, 0)

    def get_partition_lag(self, partition: int) -> int:
        """Calculates lag: High Watermark - Committed Offset."""
        high_watermarks = self.producer.get_high_watermarks()
        hwm = high_watermarks.get(partition, 0)
        committed = self.committed_offsets.get(partition, 0)
        return max(0, hwm - committed)

    def get_total_lag(self) -> int:
        """Computes aggregate lag across all assigned partitions."""
        return sum(self.get_partition_lag(p) for p in self.assigned_partitions)

    def verify_zero_lag(self) -> bool:
        """Verifies zero consumer lag before downstream batch handoff."""
        return self.get_total_lag() == 0

    def get_metrics(self) -> dict[str, Any]:
        """Exports consumer telemetry for observability pipelines."""
        return {
            "consumer_id": self.consumer_id,
            "group_id": self.group_id,
            "assigned_partitions": self.assigned_partitions,
            "committed_offsets": dict(self.committed_offsets),
            "current_offsets": dict(self.current_offsets),
            "total_lag": self.get_total_lag(),
            "zero_lag_verified": self.verify_zero_lag(),
        }
