from typing import Literal

from pydantic import BaseModel, Field


class StructuredTriageOutput(BaseModel):
    category: Literal["hardware", "software", "access_control", "billing", "security"]
    urgency: Literal["low", "medium", "high", "critical"]
    recommended_tool: str
    requires_human_approval: bool
    reasoning: str = Field(description="One sentence justification")
