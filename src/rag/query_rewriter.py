class QueryRewriter:
    @staticmethod
    def expand_query(raw_query: str) -> list[str]:
        expanded = [raw_query]
        lowered = raw_query.lower()
        if "oom" in lowered or "memory" in lowered:
            expanded.append(f"{raw_query} CUDA Out of Memory memory leak heap allocation")
        if "latency" in lowered or "slow" in lowered:
            expanded.append(f"{raw_query} p95 p99 response time CPU throttling bottleneck")
        return expanded
