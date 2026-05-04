from __future__ import annotations

import asyncio

from rag_engine.config import DocumentChunk
from rag_engine.vectorstore.chroma_store import ChromaStore


class _FakeChromaClient:
    def get_max_batch_size(self) -> int:
        return 2


class _FakeCollection:
    def __init__(self) -> None:
        self.calls = []

    def add(self, *, ids, embeddings, documents, metadatas) -> None:
        self.calls.append(
            {
                "ids": list(ids),
                "embeddings": list(embeddings),
                "documents": list(documents),
                "metadatas": list(metadatas),
            }
        )

    def count(self) -> int:
        return sum(len(call["ids"]) for call in self.calls)


def _chunk(index: int) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"chunk-{index}",
        case_reference="case-1",
        chunk_index=index,
        text=f"Chunk {index}",
        year=2026,
    )


def test_add_chunks_batches_at_chroma_client_limit() -> None:
    store = object.__new__(ChromaStore)
    store._client = _FakeChromaClient()
    store._collection = _FakeCollection()
    store._stats = {"chunks_added": 0, "queries": 0}

    chunks = [_chunk(i) for i in range(5)]
    embeddings = [[float(i)] for i in range(5)]

    asyncio.run(store.add_chunks(chunks, embeddings))

    assert [call["ids"] for call in store._collection.calls] == [
        ["chunk-0", "chunk-1"],
        ["chunk-2", "chunk-3"],
        ["chunk-4"],
    ]
    assert store._stats["chunks_added"] == 5
