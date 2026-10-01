import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IncidentReport:
    incident_id: str
    service_name: str
    severity: str  # "P1" or "P2"
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

    def __init__(self):
        self.incident_counter = 1

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

        # 1. Filter relevant error logs
        error_logs = [
            f"[{log.get('level', 'ERROR')}] {log.get('message', '')}"
            for log in recent_logs
            if log.get("service") == service_name or log.get("level") in ("ERROR", "CRITICAL")
        ]

        # 2. Correlate recent git commits
        culprit_commits = [
            c for c in recent_commits if service_name in c.get("service", service_name)
        ]

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
            runbook = self.RUNBOOKS["ERROR_BURST"]
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
            runbook = self.RUNBOOKS["LATENCY_SPIKE"]
            action_plan = [
                f"Inspect active connections on {service_name} backing store.",
                "Flush stale session caches in Redis cluster.",
                "Verify database lock contention on customer-facing tables.",
            ]

        # 5. Blast Radius Mapping
        blast_radius = [service_name]
        if service_name in ("api-gateway", "auth-service"):
            blast_radius.extend(["checkout-service", "rag-retrieval", "web-frontend"])
        elif service_name == "rag-retrieval":
            blast_radius.append("api-gateway")

        return IncidentReport(
            incident_id=incident_id,
            service_name=service_name,
            severity=severity,
            root_cause_summary=root_cause,
            correlated_logs=error_logs[:5],
            correlated_commits=culprit_commits[:2],
            blast_radius=blast_radius,
            recommended_runbook=runbook,
            action_plan=action_plan,
        )
