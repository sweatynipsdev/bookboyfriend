"""Scraper dispatch — routes URLs to the appropriate source-specific scraper."""

from __future__ import annotations

import asyncio
import logging

from backend.scraper.base import ScrapedContent
from backend.scraper import fandom, goodreads, generic

logger = logging.getLogger(__name__)


async def scrape_url(url: str) -> ScrapedContent:
    """Scrape a single URL using the appropriate scraper."""
    if fandom.can_handle(url):
        return await fandom.scrape(url)
    if goodreads.can_handle(url):
        return await goodreads.scrape(url)
    return await generic.scrape(url)


async def scrape_urls(urls: list[str]) -> list[ScrapedContent]:
    """Scrape multiple URLs concurrently.

    Returns results in the same order as the input URLs.
    Failed scrapes are included with success=False.
    """
    tasks = [scrape_url(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scraped: list[ScrapedContent] = []
    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            logger.error(f"Scraper exception for {url}: {result}")
            scraped.append(ScrapedContent(
                url=url, title="", success=False, error=str(result),
            ))
        else:
            scraped.append(result)

    return scraped
