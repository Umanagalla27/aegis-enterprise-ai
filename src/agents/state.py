from typing import Annotated, Any, Literal

from pydantic import BaseModel
from typing_extensions import TypedDict


class IncidentTicket(BaseModel):
    ticket_id: str
    service_name: str
    description: str
    reported_by: str = "Automated-Anomaly-Detector"


class TriageOutput(BaseModel):
    severity: Literal["P1", "P2", "P3", "P4"]
    category: str
    requires_human_approval: bool
    summary: str


class RemediationAction(BaseModel):
    action_type: str
    parameters: dict[str, Any]
    status: Literal["pending", "approved", "rejected", "executed"]
    result: str | None = None


def append_remediations(
    existing: list[RemediationAction] | None, new: list[RemediationAction]
) -> list[RemediationAction]:
    """Appends new actions, but updates an action in place when the same action
    (same type and parameters) comes back with a new status.

    Previously the execution node's status update was appended as a second copy, so an
    approved rollback appeared twice (approved + executed) and a rejection twice.
    """
    merged = list(existing or [])
    for action in new:
        for i, old in enumerate(merged):
            if (old.action_type, old.parameters) == (action.action_type, action.parameters):
                merged[i] = action
                break
        else:
            merged.append(action)
    return merged


class AegisAgentState(TypedDict):
    ticket: IncidentTicket
    security_flagged: bool
    triage: TriageOutput | None
    kb_research: str | None
    rca_diagnosis: str | None
    actions: Annotated[list[RemediationAction], append_remediations]
    review_status: Literal["pending", "approved", "escalated", "resolved"]
    resolution_notes: str | None
