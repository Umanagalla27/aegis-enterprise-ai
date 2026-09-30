import torch

from src.models.transformer_scratch import TinyTransformerBlock
from src.rag.chunking import TokenAwareChunker
from src.rag.graph_rag import TopologicalGraphRAG
from src.rag.hybrid_retriever import AegisHybridRetriever
from src.rag.query_rewriter import QueryRewriter


def test_transformer_from_scratch():
    block = TinyTransformerBlock(d_model=64, num_heads=4)
    x = torch.randn(2, 10, 64)
    out = block(x)
    assert out.shape == (2, 10, 64)


def test_token_aware_chunking():
    chunker = TokenAwareChunker(chunk_size=50, chunk_overlap=10)
    text = "Enterprise AI operations platform requires hybrid vector search. " * 10
    chunks = chunker.chunk_text(text, source="test_doc")
    assert len(chunks) > 1
    assert chunks[0].token_count <= 55


def test_topological_graph_rag():
    graph_rag = TopologicalGraphRAG()
    # If rag-retrieval fails, api-gateway is affected
    blast_radius = graph_rag.get_blast_radius("rag-retrieval")
    assert "api-gateway" in blast_radius


def test_query_rewriting():
    expanded = QueryRewriter.expand_query("High OOM errors in service")
    assert len(expanded) == 2
    assert "CUDA" in expanded[1]


def test_hybrid_retriever_index_and_search():
    retriever = AegisHybridRetriever()
    sample_docs = [
        {
            "chunk_id": "c1",
            "text": "SOP-401: Production PostgreSQL access requires director approval.",
            "metadata": {"type": "sop"},
        },
        {
            "chunk_id": "c2",
            "text": "Runbook 102: To resolve GPU CUDA Out of Memory, reduce batch size to 32.",
            "metadata": {"type": "runbook"},
        },
    ]
    retriever.index_documents(sample_docs)
    results = retriever.search_hybrid("How to fix GPU Out of Memory?", top_k=1)
    assert len(results) == 1
    assert "c2" == results[0].chunk_id
