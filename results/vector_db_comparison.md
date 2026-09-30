# Vector Database Architectural Comparison Spike

| Vector Database | Type | Index | p95 Latency | Operational Effort | Best Fit |
|---|---|---|---|---|---|
| **pgvector** | Relational Extension | **HNSW** | **~5 ms** | **Near Zero (re-uses PostgreSQL)** | **Enterprise default; ACID transactions, joins** |
| **FAISS** | In-Memory Library | Flat / IVFFlat | **< 1 ms** | Requires custom cluster management | Ultra-fast local embedding baselines |
| **Pinecone** | Fully Managed SaaS | Proprietary | ~35 ms | Zero maintenance (hosted) | Rapid MVPs with zero infra ownership |
| **Milvus** | Distributed Vector DB | HNSW / Knowhere | ~12 ms | High (requires K8s, MinIO, Pulsar/Kafka) | 100M+ vector hyperscale search |
| **Weaviate** | Vector Search Engine | HNSW + BM25 | ~15 ms | Medium (Docker / K8s) | Native GraphQL multimodal workflows |
