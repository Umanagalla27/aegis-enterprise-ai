import hashlib
from dataclasses import dataclass
from typing import Any

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class DocumentChunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    token_count: int


class TokenAwareChunker:
    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=lambda t: len(self.tokenizer.encode(t)),
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk_text(self, text: str, source: str = "doc") -> list[DocumentChunk]:
        raw_chunks = self.splitter.split_text(text)
        chunks = []
        for idx, c in enumerate(raw_chunks):
            cid = hashlib.sha256(f"{source}:{idx}:{c[:30]}".encode()).hexdigest()[:16]
            chunks.append(
                DocumentChunk(
                    chunk_id=cid,
                    text=c,
                    metadata={"source": source, "index": idx},
                    token_count=len(self.tokenizer.encode(c)),
                )
            )
        return chunks
