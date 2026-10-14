import logging
from dataclasses import dataclass
from typing import Any

from src.agents.incident_classifier import classify_fault
from src.rag.graph_rag import TopologicalGraphRAG

logger = logging.getLogger(__name__)


@dataclass
class IncidentReport:
    incident_id: str
    service_name: str
    severity: str  # "P1" or "P2"
    fault_type: str
    root_cause_summary: str
    correlated_logs: list[str]
    correlated_commits: list[dict[str, str]]
    blast_radius: list[str]
    recommended_runbook: str
    action_plan: list[str]


class RootCauseAnalysisAgent:
    """
    Autonomous Incident Diagnosis Agent:
    Correlates telemetry spikes with service error logs and recent git commit deployments.
    """

    RUNBOOKS = {
        "LATENCY_SPIKE": "runbooks/mitigate_db_pool_exhaustion.md",
        "OOM_CRASH": "runbooks/remediate_memory_leak.md",
        "ERROR_BURST": "runbooks/rollback_canary_deployment.md",
    }

    def __init__(self, topology: TopologicalGraphRAG | None = None):
        self.incident_counter = 1
        self.topology = topology or TopologicalGraphRAG()

    def diagnose_incident(
        self,
        service_name: str,
        anomaly_details: dict[str, Any],
        recent_logs: list[dict[str, Any]] | None = None,
        recent_commits: list[dict[str, str]] | None = None,
    ) -> IncidentReport:
        """Performs full root-cause investigation across metrics, logs, and deployment events."""
        incident_id = f"INC-{self.incident_counter:04d}"
        self.incident_counter += 1

        recent_logs = recent_logs or []
        recent_commits = recent_commits or []

        # 1. Filter relevant error logs: only this service, only ERROR/CRITICAL.
        #    (Previously any ERROR from any service was pulled in, and any log from
        #    this service even at INFO level.)
        error_logs = [
            f"[{log.get('level', 'ERROR')}] {log.get('message', '')}"
            for log in recent_logs
            if log.get("service") == service_name
            and log.get("level", "ERROR") in ("ERROR", "CRITICAL")
        ]

        # 2. Correlate recent git commits: exact service match only.
        #    (Previously a substring check meant service "api" blamed "api-gateway"
        #    commits, and commits with no service field were blamed on everything.)
        culprit_commits = [c for c in recent_commits if c.get("service") == service_name]

        # Classify the fault from the log text so the runbook matches the symptom.
        fault_type = classify_fault(" ".join(error_logs))

        # 3. Determine incident severity
        is_p1 = (
            anomaly_details.get("severity") == "CRITICAL"
            or anomaly_details.get("observed_value", 0) > 1000.0
            or len(error_logs) >= 3
        )
        severity = "P1" if is_p1 else "P2"

        # 4. Formulate Root Cause Hypothesis
        if culprit_commits:
            commit_info = culprit_commits[0]
            root_cause = (
                f"Deployment regression in commit '{commit_info.get('commit_hash')}' "
                f"by {commit_info.get('author')}: '{commit_info.get('message')}'. "
                f"Triggered resource exhaustion in {service_name}."
            )
            runbook = self.RUNBOOKS.get(fault_type, self.RUNBOOKS["ERROR_BURST"])
            action_plan = [
                f"Initiate canary rollback for commit {commit_info.get('commit_hash')}.",
                f"Scale up {service_name} replicas by 50% to absorb pending request buffer.",
                "Drain connection pool and verify P95 latency returns under 60ms.",
            ]
        else:
            root_cause = (
                f"Downstream service dependency bottleneck or query contention in {service_name}. "
                f"Observed value: {anomaly_details.get('observed_value')}ms."
            )
            runbook = self.RUNBOOKS.get(fault_type, self.RUNBOOKS["LATENCY_SPIKE"])
            action_plan = [
                f"Inspect active connections on {service_name} backing store.",
                "Flush stale session caches in Redis cluster.",
                "Verify database lock contention on customer-facing tables.",
            ]

        # 5. Blast Radius Mapping from the same service graph Graph RAG uses
        #    (was a hard-coded list naming services that are not in the graph).
        blast_radius = [service_name, *sorted(self.topology.get_blast_radius(service_name))]

        return IncidentReport(
            incident_id=incident_id,
            service_name=service_name,
            severity=severity,
            fault_type=fault_type,
            root_cause_summary=root_cause,
            correlated_logs=error_logs[:5],
            correlated_commits=culprit_commits[:2],
            blast_radius=blast_radius,
            recommended_runbook=runbook,
            action_plan=action_plan,
        )
