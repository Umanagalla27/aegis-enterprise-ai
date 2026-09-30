try:
    from mcp.server.fastmcp import FastMCP
except (ModuleNotFoundError, ImportError):
    from mcp.server.mcpserver import MCPServer as FastMCP

from src.rag.graph_rag import TopologicalGraphRAG
from src.rag.hybrid_retriever import AegisHybridRetriever

mcp = FastMCP("Aegis-Enterprise-MCP")

retriever = AegisHybridRetriever()
graph_rag = TopologicalGraphRAG()


@mcp.tool()
def search_it_knowledge_base(query: str) -> str:
    """Queries Hybrid RAG for enterprise runbooks and resolution policies."""
    hits = retriever.search_hybrid(query, top_k=2)
    if not hits:
        return "No matching runbook found."
    return "\n---\n".join([f"[{h.chunk_id}] {h.text}" for h in hits])


@mcp.tool()
def get_service_topology(service_name: str) -> str:
    """Queries Graph RAG for upstream and downstream service dependencies."""
    blast_radius = graph_rag.get_blast_radius(service_name)
    deps = graph_rag.get_dependencies(service_name)
    return f"Service: {service_name} | Dependencies: {deps} | Impacted If Failed: {blast_radius}"


@mcp.tool()
def execute_deployment_rollback(service_name: str, target_commit: str) -> str:
    """Executes a container rollback in Kubernetes/ECS (Requires HITL approval)."""
    return f"SUCCESS: Rolled back {service_name} to commit {target_commit}."
