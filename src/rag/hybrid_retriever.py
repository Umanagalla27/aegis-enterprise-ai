import math
import re
from dataclasses import dataclass, field
from typing import Any

from rank_bm25 import BM25Okapi, BM25Plus


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


class AegisHybridRetriever:
    """Enterprise Hybrid Retriever combining BM25 lexical search and dense semantic

    similarity, fused using Reciprocal Rank Fusion (RRF).
    """

    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k
        self.documents: list[dict[str, Any]] = []
        self.bm25: BM25Plus | BM25Okapi | None = None
        self.tokenized_corpus: list[list[str]] = []

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def index_documents(self, documents: list[dict[str, Any] | Any]) -> None:
        """Indexes raw documents or DocumentChunk instances for hybrid retrieval."""
        self.documents = []
        self.tokenized_corpus = []

        for doc in documents:
            if hasattr(doc, "chunk_id"):
                chunk_id = doc.chunk_id
                text = doc.text
                metadata = getattr(doc, "metadata", {})
            else:
                chunk_id = doc["chunk_id"]
                text = doc["text"]
                metadata = doc.get("metadata", {})

            self.documents.append(
                {"chunk_id": chunk_id, "text": text, "metadata": metadata}
            )
            self.tokenized_corpus.append(self._tokenize(text))

        if self.tokenized_corpus:
            # Use BM25Plus to prevent zero-IDF edge cases on small corpora
            self.bm25 = BM25Plus(self.tokenized_corpus)
        else:
            self.bm25 = None

    def _compute_dense_similarity(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        """Calculates token-level cosine similarity as a fast dense surrogate."""
        if not query_tokens or not doc_tokens:
            return 0.0
        query_set = set(query_tokens)
        doc_set = set(doc_tokens)
        intersection = query_set.intersection(doc_set)
        if not intersection:
            return 0.0
        return len(intersection) / math.sqrt(len(query_set) * len(doc_set))

    def search_sparse(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Performs BM25 sparse lexical search."""
        if not self.bm25 or not self.documents:
            return []

        query_tokens = self._tokenize(query)
        scores = self.bm25.get_scores(query_tokens)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results = []
        for idx in ranked_indices[:top_k]:
            doc = self.documents[idx]
            results.append(
                RetrievedChunk(
                    chunk_id=doc["chunk_id"],
                    text=doc["text"],
                    metadata=doc["metadata"],
                    score=float(scores[idx]),
                )
            )
        return results

    def search_dense(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Performs dense semantic similarity ranking."""
        if not self.documents:
            return []

        query_tokens = self._tokenize(query)
        scores = [
            self._compute_dense_similarity(query_tokens, doc_toks)
            for doc_toks in self.tokenized_corpus
        ]
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results = []
        for idx in ranked_indices[:top_k]:
            doc = self.documents[idx]
            results.append(
                RetrievedChunk(
                    chunk_id=doc["chunk_id"],
                    text=doc["text"],
                    metadata=doc["metadata"],
                    score=float(scores[idx]),
                )
            )
        return results

    def search_hybrid(
        self, query: str, top_k: int = 5, rrf_k: int | None = None
    ) -> list[RetrievedChunk]:
        """Combines BM25 and dense results using Reciprocal Rank Fusion (RRF).

        RRF Score: sum(1 / (k + rank_i))
        """
        if not self.documents:
            return []

        k = rrf_k if rrf_k is not None else self.rrf_k
        sparse_results = self.search_sparse(query, top_k=len(self.documents))
        dense_results = self.search_dense(query, top_k=len(self.documents))

        rrf_scores: dict[str, float] = {doc["chunk_id"]: 0.0 for doc in self.documents}

        for rank, res in enumerate(sparse_results):
            if res.score > 0:
                rrf_scores[res.chunk_id] += 1.0 / (k + rank + 1)

        for rank, res in enumerate(dense_results):
            if res.score > 0:
                rrf_scores[res.chunk_id] += 1.0 / (k + rank + 1)

        doc_lookup = {doc["chunk_id"]: doc for doc in self.documents}
        sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        results = []
        for cid in sorted_ids[:top_k]:
            doc = doc_lookup[cid]
            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    text=doc["text"],
                    metadata=doc["metadata"],
                    score=rrf_scores[cid],
                )
            )
        return results
