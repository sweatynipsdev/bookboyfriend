"""Embed scraped character content into ChromaDB for RAG-enhanced chat."""

from __future__ import annotations

import logging

from backend.ingestion.loader import TextBlock
from backend.ingestion.chunker import chunk_text_blocks
from backend.ingestion.embedder import embed_and_store, delete_collection
from backend.scraper.base import ScrapedContent

logger = logging.getLogger(__name__)


def embed_character_content(
    character_id: str,
    scraped: list[ScrapedContent],
) -> int:
    """Chunk and embed scraped content into a character's ChromaDB collection.

    Args:
        character_id: The character's UUID (used as the collection namespace).
        scraped: List of scraped content (only successful ones are used).

    Returns:
        Total number of chunks stored.
    """
    text_blocks = []
    for sc in scraped:
        if not sc.success:
            continue
        for section in sc.sections:
            text_blocks.append(TextBlock(
                text=section.text,
                metadata={
                    "source_url": section.source_url,
                    "heading": section.heading,
                    "character_id": character_id,
                },
            ))

    if not text_blocks:
        logger.warning(f"No text blocks to embed for character {character_id}")
        return 0

    chunked_docs = chunk_text_blocks(text_blocks)

    # Clear existing embeddings for this character (safe on re-build)
    try:
        delete_collection(character_id)
    except Exception:
        pass

    total = embed_and_store(
        documents=chunked_docs,
        notebook_id=character_id,
        doc_id="wiki",
    )

    logger.info(f"Embedded {total} chunks for character {character_id}")
    return total
