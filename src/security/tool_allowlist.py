class ToolAccessController:
    ROLE_PERMISSIONS = {
        "triage_agent": [],
        "research_agent": ["search_it_knowledge_base", "get_service_topology"],
        "rca_agent": ["query_prometheus_metrics", "search_application_logs"],
        "action_agent": ["execute_container_restart", "execute_deployment_rollback"],
    }

    @classmethod
    def authorize(cls, agent_role: str, tool_name: str) -> bool:
        allowed = cls.ROLE_PERMISSIONS.get(agent_role, [])
        return tool_name in allowed
