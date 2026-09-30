from dataclasses import dataclass

import networkx as nx


@dataclass
class ServiceDependency:
    upstream: str
    downstream: str
    relation: str


class TopologicalGraphRAG:
    """Graph RAG capturing microservice architectures, databases, and dependencies."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self._build_default_topology()

    def _build_default_topology(self):
        edges = [
            ("api-gateway", "auth-service", "authenticates_via"),
            ("api-gateway", "rag-retrieval", "queries_kb"),
            ("rag-retrieval", "aegis-postgres", "fetches_vectors"),
            ("rag-retrieval", "aegis-redis", "cache_lookup"),
            ("auth-service", "db-writer", "persists_tokens"),
            ("db-writer", "aegis-postgres", "writes_audit"),
        ]
        for src, dst, rel in edges:
            self.graph.add_edge(src, dst, relation=rel)

    def get_blast_radius(self, failing_service: str) -> list[str]:
        """Finds all services that will fail if this service goes down (upstream cascade)."""
        if failing_service not in self.graph:
            return []
        # Reverse edges to find who depends on failing_service
        rev_graph = self.graph.reverse()
        return list(nx.descendants(rev_graph, failing_service))

    def get_dependencies(self, service: str) -> list[str]:
        """Finds all services that this service requires to function."""
        if service not in self.graph:
            return []
        return list(nx.descendants(self.graph, service))
