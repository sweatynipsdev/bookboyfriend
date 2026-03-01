"""Embed documents and store in ChromaDB.

Each notebook gets its own ChromaDB collection. Embeddings are generated
automatically by ChromaDB using sentence-transformers.
"""

from __future__ import annotations

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from backend.config import settings

# Module-level singletons (lazy initialized)
_chroma_client: chromadb.PersistentClient | None = None
_embedding_fn: SentenceTransformerEmbeddingFunction | None = None


def _get_chroma_client() -> chromadb.PersistentClient:
    """Get or create the ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_path)
    return _chroma_client


def _get_embedding_fn() -> SentenceTransformerEmbeddingFunction:
    """Get or create the sentence-transformer embedding function."""
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _embedding_fn


def get_collection(notebook_id: str) -> chromadb.Collection:
    """Get or create a ChromaDB collection for a notebook.

    Args:
        notebook_id: The notebook's UUID string.

    Returns:
        A ChromaDB Collection with sentence-transformer embeddings.
    """
    client = _get_chroma_client()
    return client.get_or_create_collection(
        name=f"notebook_{notebook_id}",
        embedding_function=_get_embedding_fn(),
    )


def embed_and_store(
    documents: list,
    notebook_id: str,
    doc_id: str = "",
) -> int:
    """Embed documents and store them in the notebook's ChromaDB collection.

    Args:
        documents: LlamaIndex Document objects (chunked).
        notebook_id: Target notebook UUID.
        doc_id: Document UUID for unique chunk IDs (prevents collision on re-ingestion).

    Returns:
        Number of chunks stored.
    """
    collection = get_collection(notebook_id)

    texts = [doc.text for doc in documents]
    metadatas = [doc.metadata for doc in documents]

    # Use doc-specific IDs to prevent collisions when re-ingesting
    id_prefix = f"{notebook_id}_{doc_id}" if doc_id else notebook_id
    ids = [f"{id_prefix}_chunk_{i}" for i in range(len(documents))]

    # ChromaDB handles embedding via the collection's embedding_function
    collection.upsert(
        documents=texts,
        metadatas=metadatas,
        ids=ids,
    )

    return len(documents)


def delete_collection(notebook_id: str) -> None:
    """Delete a notebook's ChromaDB collection."""
    client = _get_chroma_client()
    try:
        client.delete_collection(name=f"notebook_{notebook_id}")
    except ValueError:
        pass  # Collection doesn't exist


def delete_document_chunks(notebook_id: str, doc_id: str) -> None:
    """Delete all chunks belonging to a specific document."""
    collection = get_collection(notebook_id)
    # Get all IDs matching this document prefix
    prefix = f"{notebook_id}_{doc_id}_chunk_"
    results = collection.get(where={"$or": []})  # noqa: we'll use ID filtering
    # ChromaDB supports getting by ID prefix via the where clause on IDs
    all_ids = collection.get()["ids"]
    matching_ids = [id_ for id_ in all_ids if id_.startswith(prefix)]
    if matching_ids:
        collection.delete(ids=matching_ids)
