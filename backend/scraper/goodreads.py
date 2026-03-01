"""Goodreads scraper — best-effort extraction of book/character descriptions."""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from backend.scraper.base import ScrapedContent, ScrapedSection

logger = logging.getLogger(__name__)

_GOODREADS_PATTERNS = ["goodreads.com"]


def can_handle(url: str) -> bool:
    return any(p in url.lower() for p in _GOODREADS_PATTERNS)


async def scrape(url: str) -> ScrapedContent:
    """Attempt to scrape a Goodreads page.

    Targets book description and genre tags.
    Gracefully degrades if blocked by anti-bot measures.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning(f"Goodreads blocked or failed for {url}: {e}")
        return ScrapedContent(
            url=url, title="", success=False,
            error=f"Goodreads fetch failed (likely anti-bot): {e}",
        )

    if "cf-browser-verification" in response.text or response.status_code == 403:
        return ScrapedContent(
            url=url, title="", success=False,
            error="Goodreads returned a Cloudflare challenge page",
        )

    soup = BeautifulSoup(response.text, "lxml")

    title = ""
    title_tag = soup.select_one("h1[data-testid='bookTitle']") or soup.select_one("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)

    sections: list[ScrapedSection] = []

    # Book description
    desc = (
        soup.select_one("[data-testid='description']")
        or soup.select_one(".BookPageMetadataSection__description")
    )
    if desc:
        sections.append(ScrapedSection(
            heading="Book Description", text=desc.get_text(strip=True), source_url=url,
        ))

    # Genre tags
    genres = soup.select(".BookPageMetadataSection__genreButton a")
    if genres:
        genre_list = ", ".join(g.get_text(strip=True) for g in genres[:10])
        sections.append(ScrapedSection(
            heading="Genres", text=genre_list, source_url=url,
        ))

    raw_text = "\n\n".join(f"## {s.heading}\n{s.text}" for s in sections)

    return ScrapedContent(
        url=url, title=title, sections=sections,
        raw_text=raw_text, success=len(sections) > 0,
        error="" if sections else "No content extracted from Goodreads page",
    )
