from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.agents.state import AegisAgentState, RemediationAction, TriageOutput
from src.mcp.server import (
    execute_deployment_rollback,
    get_service_topology,
    search_it_knowledge_base,
)
from src.security.injection_defense import InjectionDefenseEngine
from src.security.presidio_redactor import EnterprisePIIRedactor
from src.security.tool_allowlist import ToolAccessController


def security_node(state: AegisAgentState) -> dict:
    raw = state["ticket"].description
    is_attack, reason = InjectionDefenseEngine.is_adversarial(raw)
    if is_attack:
        return {
            "security_flagged": True,
            "review_status": "escalated",
            "resolution_notes": f"QUARANTINED: {reason}",
        }
    sanitized = EnterprisePIIRedactor.redact(raw)
    state["ticket"].description = sanitized.clean_text
    return {"security_flagged": False}


def triage_node(state: AegisAgentState) -> dict:
    desc = state["ticket"].description.lower()
    if "oom" in desc or "cuda" in desc or "critical" in desc:
        sev = "P1"
        needs_approval = True
    elif "timeout" in desc or "high latency" in desc:
        sev = "P2"
        needs_approval = True
    else:
        sev = "P3"
        needs_approval = False

    triage = TriageOutput(
        severity=sev,
        category="infrastructure",
        requires_human_approval=needs_approval,
        summary=f"Triaged as {sev} incident.",
    )
    return {"triage": triage}


def research_node(state: AegisAgentState) -> dict:
    svc = state["ticket"].service_name
    kb_info = search_it_knowledge_base(state["ticket"].description)
    topo = get_service_topology(svc)
    return {"kb_research": f"{kb_info}\nTopology: {topo}"}


def rca_node(state: AegisAgentState) -> dict:
    desc = state["ticket"].description
    if "oom" in desc.lower():
        diagnosis = "Root Cause: Batch size allocation exceeded GPU memory limits."
    else:
        diagnosis = "Root Cause: Database connection pool saturation."
    return {"rca_diagnosis": diagnosis}


def action_planning_node(state: AegisAgentState) -> dict:
    triage = state["triage"]
    action_type = "execute_deployment_rollback"

    # Enforce role-based tool authorization
    if not ToolAccessController.authorize("action_agent", action_type):
        rejected_action = RemediationAction(
            action_type=action_type,
            parameters={"service_name": state["ticket"].service_name},
            status="rejected",
            result="Tool access denied for role action_agent.",
        )
        return {"actions": [rejected_action]}

    action = RemediationAction(
        action_type=action_type,
        parameters={
            "service_name": state["ticket"].service_name,
            "target_commit": "prev_stable",
        },
        status="pending" if triage.requires_human_approval else "approved",
    )

    if triage.requires_human_approval:
        # HITL Interrupt
        action_dict = (
            action.model_dump() if hasattr(action, "model_dump") else action.dict()
        )
        decision = interrupt({
            "prompt": f"Authorize remediation rollback for {state['ticket'].service_name}?",
            "action": action_dict,
        })
        if decision.get("approved") is True:
            action.status = "approved"
            action.result = f"Approved by {decision.get('reviewer', 'SRE_Lead')}"
        else:
            action.status = "rejected"
            action.result = "Denied by reviewer."

    return {"actions": [action]}


def execution_node(state: AegisAgentState) -> dict:
    actions = state.get("actions", [])
    if not actions:
        return {"review_status": "resolved"}
    latest = (
        actions[-1].model_copy()
        if hasattr(actions[-1], "model_copy")
        else actions[-1].copy()
    )

    if latest.status == "approved":
        res = execute_deployment_rollback(**latest.parameters)
        latest.status = "executed"
        latest.result = res
        return {
            "actions": [latest],
            "review_status": "resolved",
            "resolution_notes": "Mitigation applied successfully.",
        }
    return {
        "actions": [latest],
        "review_status": "escalated",
        "resolution_notes": "Action was rejected.",
    }


def check_security(state: AegisAgentState) -> str:
    return "quarantine" if state.get("security_flagged") else "triage"


def build_aegis_graph():
    workflow = StateGraph(AegisAgentState)

    workflow.add_node("security_node", security_node)
    workflow.add_node("triage_node", triage_node)
    workflow.add_node("research_node", research_node)
    workflow.add_node("rca_node", rca_node)
    workflow.add_node("action_planning_node", action_planning_node)
    workflow.add_node("execution_node", execution_node)

    workflow.add_edge(START, "security_node")
    workflow.add_conditional_edges(
        "security_node",
        check_security,
        {"quarantine": END, "triage": "triage_node"},
    )
    workflow.add_edge("triage_node", "research_node")
    workflow.add_edge("research_node", "rca_node")
    workflow.add_edge("rca_node", "action_planning_node")
    workflow.add_edge("action_planning_node", "execution_node")
    workflow.add_edge("execution_node", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
