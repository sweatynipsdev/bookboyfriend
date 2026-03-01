"""Smart text chunking using LlamaIndex SentenceSplitter."""

from llama_index.core import Document as LlamaDocument
from llama_index.core.node_parser import SentenceSplitter

from backend.config import settings
from backend.ingestion.loader import TextBlock


def chunk_text_blocks(
    blocks: list[TextBlock],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[LlamaDocument]:
    """Split text blocks into chunked LlamaIndex Documents.

    Args:
        blocks: TextBlocks from the loader.
        chunk_size: Token chunk size (default from settings).
        chunk_overlap: Token overlap between chunks (default from settings).

    Returns:
        List of LlamaIndex Document objects with preserved metadata.
    """
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap or settings.chunk_overlap

    # Convert TextBlocks to LlamaIndex Documents
    documents = [LlamaDocument(text=block.text, metadata=block.metadata) for block in blocks]

    # Split using SentenceSplitter
    splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    nodes = splitter.get_nodes_from_documents(documents)

    # Convert nodes back to Documents with chunk index metadata
    chunked_docs = []
    for i, node in enumerate(nodes):
        metadata = dict(node.metadata)
        metadata["chunk_index"] = i
        chunked_docs.append(
            LlamaDocument(text=node.get_content(), metadata=metadata)
        )

    return chunked_docs
