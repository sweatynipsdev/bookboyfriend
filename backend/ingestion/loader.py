"""Data types for the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TextBlock:
    """A block of text with metadata, used as input to the chunker."""

    text: str
    metadata: dict = field(default_factory=dict)
