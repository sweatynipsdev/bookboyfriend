"""Query ChromaDB and return relevant chunks with relevance scores."""

from __future__ import annotations

from dataclasses import dataclass

from backend.config import settings
from backend.ingestion.embedder import get_collection


@dataclass
class RetrievedChunk:
    """A chunk retrieved from the vector store with its relevance score."""

    text: str
    metadata: dict
    score: float


def retrieve(
    query: str,
    notebook_id: str,
    top_k: int | None = None,
    score_threshold: float = 0.3,
) -> list[RetrievedChunk]:
    """Retrieve relevant chunks from a notebook's vector store.

    Args:
        query: The user's question.
        notebook_id: Which notebook to search.
        top_k: Number of results to return (default from settings).
        score_threshold: Minimum relevance score (0 to 1).

    Returns:
        List of RetrievedChunk objects, sorted by relevance (best first).
    """
    top_k = top_k or settings.top_k_results
    collection = get_collection(notebook_id)

    # Skip if collection is empty
    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    if results and results["documents"] and results["documents"][0]:
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for text, metadata, distance in zip(documents, metadatas, distances):
            # ChromaDB returns L2 distances by default.
            # Convert to similarity: lower distance = higher score.
            score = 1.0 / (1.0 + distance)

            if score >= score_threshold:
                chunks.append(
                    RetrievedChunk(text=text, metadata=metadata, score=score)
                )

    chunks.sort(key=lambda c: c.score, reverse=True)
    return chunks
