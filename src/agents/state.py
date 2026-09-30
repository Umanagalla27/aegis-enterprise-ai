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
    if existing is None:
        return new
    return existing + new


class AegisAgentState(TypedDict):
    ticket: IncidentTicket
    security_flagged: bool
    triage: TriageOutput | None
    kb_research: str | None
    rca_diagnosis: str | None
    actions: Annotated[list[RemediationAction], append_remediations]
    review_status: Literal["pending", "approved", "escalated", "resolved"]
    resolution_notes: str | None
