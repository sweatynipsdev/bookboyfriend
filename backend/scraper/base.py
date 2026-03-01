"""Scraper shared data types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScrapedSection:
    """A named section of scraped content (e.g., 'Personality', 'History')."""

    heading: str
    text: str
    source_url: str


@dataclass
class ScrapedContent:
    """Aggregated scraped content from a single URL."""

    url: str
    title: str
    sections: list[ScrapedSection] = field(default_factory=list)
    raw_text: str = ""
    success: bool = True
    error: str = ""
