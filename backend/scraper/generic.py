"""Generic URL scraper — extracts article content from arbitrary web pages."""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from backend.scraper.base import ScrapedContent, ScrapedSection

logger = logging.getLogger(__name__)


async def scrape(url: str) -> ScrapedContent:
    """Scrape an arbitrary URL, extracting the main article content."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BookBoyfriend/1.0)",
                "Accept": "text/html",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ScrapedContent(url=url, title="", success=False, error=str(e))

    soup = BeautifulSoup(response.text, "lxml")

    title = ""
    title_tag = soup.find("title") or soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Remove non-content elements
    for tag_name in ["script", "style", "nav", "footer", "header", "aside"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Find the main content container
    content = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", {"role": "main"})
        or soup.find("div", class_="content")
        or soup.body
    )

    if not content:
        return ScrapedContent(
            url=url, title=title, success=False,
            error="Could not find main content on page",
        )

    paragraphs = []
    for p in content.find_all(["p", "li", "blockquote"]):
        text = p.get_text(strip=True)
        if text and len(text) > 30:
            paragraphs.append(text)

    if not paragraphs:
        return ScrapedContent(
            url=url, title=title, success=False,
            error="No meaningful text content found",
        )

    raw_text = "\n\n".join(paragraphs)

    sections = [ScrapedSection(
        heading=title or "Page Content",
        text=raw_text,
        source_url=url,
    )]

    return ScrapedContent(
        url=url, title=title, sections=sections,
        raw_text=raw_text, success=True,
    )
