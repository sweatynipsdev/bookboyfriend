"""Fandom wiki scraper — extracts character data via the MediaWiki API.

Uses the parse API endpoint instead of scraping HTML directly,
which avoids Cloudflare blocks and returns cleaner content.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from backend.scraper.base import ScrapedContent, ScrapedSection

logger = logging.getLogger(__name__)

_FANDOM_PATTERNS = ["fandom.com"]


def can_handle(url: str) -> bool:
    return any(p in url.lower() for p in _FANDOM_PATTERNS)


def _extract_wiki_info(url: str) -> tuple[str, str]:
    """Extract the base API URL and page name from a Fandom wiki URL.

    Example: https://acourtofthornsandroses.fandom.com/wiki/Cassian
    Returns: ("https://acourtofthornsandroses.fandom.com/api.php", "Cassian")
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}/api.php"
    # Page name is the last part of the path after /wiki/
    path_parts = parsed.path.strip("/").split("/")
    page_name = path_parts[-1] if path_parts else ""
    # URL-decode the page name (e.g., "Feyre_Archeron" stays as-is for the API)
    return base, page_name


async def scrape(url: str) -> ScrapedContent:
    """Scrape a Fandom wiki character page via the MediaWiki parse API.

    Fetches rendered HTML via the API (bypasses Cloudflare) and extracts
    infobox data + section content.
    """
    api_url, page_name = _extract_wiki_info(url)
    if not page_name:
        return ScrapedContent(url=url, title="", success=False, error="Could not parse page name from URL")

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "BookBoyfriend/1.0 (character profile builder)"},
        ) as client:
            response = await client.get(api_url, params={
                "action": "parse",
                "page": page_name,
                "format": "json",
                "prop": "text|displaytitle",
            })
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch Fandom API for {url}: {e}")
        return ScrapedContent(url=url, title="", success=False, error=str(e))

    if "error" in data:
        error_msg = data["error"].get("info", "Unknown API error")
        return ScrapedContent(url=url, title="", success=False, error=error_msg)

    parse_data = data.get("parse", {})
    title = parse_data.get("displaytitle", page_name)
    # Strip any HTML tags from the display title
    title = re.sub(r"<[^>]+>", "", title).strip()
    html = parse_data.get("text", {}).get("*", "")

    if not html:
        return ScrapedContent(url=url, title=title, success=False, error="Empty page content")

    soup = BeautifulSoup(html, "lxml")
    sections: list[ScrapedSection] = []

    # Infobox
    infobox_text = _extract_infobox(soup)
    if infobox_text:
        sections.append(ScrapedSection(heading="Infobox", text=infobox_text, source_url=url))

    # Article sections
    sections.extend(_extract_sections(soup, url))

    raw_text = "\n\n".join(f"## {s.heading}\n{s.text}" for s in sections)

    return ScrapedContent(
        url=url, title=title, sections=sections,
        raw_text=raw_text, success=bool(sections),
        error="" if sections else "No content extracted",
    )


def _extract_infobox(soup: BeautifulSoup) -> str:
    """Extract key-value pairs from the Fandom portable infobox."""
    infobox = soup.select_one(".portable-infobox")
    if not infobox:
        return ""
    lines = []
    for item in infobox.select(".pi-data"):
        label = item.select_one(".pi-data-label")
        value = item.select_one(".pi-data-value")
        if label and value:
            lines.append(f"{label.get_text(strip=True)}: {value.get_text(strip=True)}")
    return "\n".join(lines)


def _extract_sections(soup: BeautifulSoup, source_url: str) -> list[ScrapedSection]:
    """Extract sections split by h2/h3 headings from the parsed HTML."""
    sections: list[ScrapedSection] = []
    current_heading = "Introduction"
    current_paragraphs: list[str] = []

    # The API response wraps content in a div; iterate top-level elements
    body = soup.find("div", class_="mw-parser-output") or soup.body or soup
    for element in body.children:
        if not isinstance(element, Tag):
            continue

        if element.name in ("h2", "h3"):
            if current_paragraphs:
                sections.append(ScrapedSection(
                    heading=current_heading,
                    text="\n".join(current_paragraphs),
                    source_url=source_url,
                ))
            heading_text = element.get_text(strip=True)
            heading_text = heading_text.replace("[edit | edit source]", "").strip()
            heading_text = re.sub(r"\[edit\]", "", heading_text).strip()
            current_heading = heading_text
            current_paragraphs = []

        elif element.name in ("p", "ul", "ol", "blockquote", "dl", "div"):
            # Skip infoboxes, nav boxes, and other non-content divs
            if element.name == "div":
                classes = element.get("class", [])
                if any(c in classes for c in ["portable-infobox", "navbox", "toc", "notice"]):
                    continue
            text = element.get_text(strip=True)
            if text and len(text) > 20:
                current_paragraphs.append(text)

    if current_paragraphs:
        sections.append(ScrapedSection(
            heading=current_heading,
            text="\n".join(current_paragraphs),
            source_url=source_url,
        ))

    return sections
