"""AI-powered character profile builder.

Takes scraped wiki content and generates a structured CharacterProfile
through multiple focused LLM calls (one per profile section).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from backend.providers import get_llm_provider
from backend.scraper.base import ScrapedContent

logger = logging.getLogger(__name__)

# Max chars of source text per LLM prompt (~1500 tokens at 4 chars/token).
_MAX_CONTEXT_CHARS = 6000


@dataclass
class ProfileBuildResult:
    """Result from the profile generation pipeline."""

    identity: dict = field(default_factory=dict)
    personality: dict = field(default_factory=dict)
    relationships: dict = field(default_factory=dict)
    arc: dict = field(default_factory=dict)
    tropes: list[str] = field(default_factory=list)
    voice_guide: str = ""
    boundaries: str = ""
    iconic_moments: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _prepare_context(scraped: list[ScrapedContent]) -> str:
    """Combine and truncate scraped content into a single context string."""
    parts = []
    for sc in scraped:
        if not sc.success or not sc.raw_text:
            continue
        parts.append(f"--- Source: {sc.url} ---\n{sc.raw_text}")

    combined = "\n\n".join(parts)
    if len(combined) > _MAX_CONTEXT_CHARS:
        combined = combined[:_MAX_CONTEXT_CHARS] + "\n\n[... truncated for length ...]"
    return combined


async def _llm_extract(
    context: str,
    character_name: str,
    series: str,
    section_prompt: str,
) -> str:
    """Make a single LLM call to extract one section of the profile."""
    llm = get_llm_provider()
    system = (
        f"You are a literary analyst building a character profile for {character_name} "
        f"from the series '{series}'. Extract information ONLY from the provided source "
        f"material. If information is not available, make reasonable inferences based on "
        f"what IS available, but do not fabricate specific events or quotes. "
        f"Respond ONLY with the requested JSON — no markdown fences, no explanation."
    )
    messages = [
        {
            "role": "user",
            "content": (
                f"Source material about {character_name}:\n\n"
                f"{context}\n\n---\n\n{section_prompt}"
            ),
        }
    ]
    return await llm.chat(messages, system=system)


def _parse_json_response(raw: str) -> dict | list | None:
    """Parse LLM JSON output, handling common formatting issues."""
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM JSON: {raw[:200]}")
        return None


async def build_profile(
    character_name: str,
    series: str,
    author: str,
    scraped: list[ScrapedContent],
) -> ProfileBuildResult:
    """Generate a full CharacterProfile from scraped content via 7 LLM calls."""
    warnings: list[str] = []
    for sc in scraped:
        if not sc.success:
            warnings.append(f"Failed to scrape {sc.url}: {sc.error}")

    source_urls = [sc.url for sc in scraped if sc.success]
    context = _prepare_context(scraped)

    if not context.strip():
        raise ValueError(
            "No usable content was scraped from any of the provided URLs."
        )

    # --- Call 1: Identity ---
    identity_raw = await _llm_extract(context, character_name, series, (
        f"Extract the IDENTITY of {character_name}. Return a JSON object with these keys:\n"
        '- "full_name": string\n'
        '- "titles": list of strings (titles, honorifics, nicknames)\n'
        '- "species": string (human, fae, vampire, etc.)\n'
        '- "age": string\n'
        '- "residence": string\n'
        '- "occupation": string\n'
        '- "powers": list of strings (supernatural abilities, if any)\n'
        '- "physical_description": string (brief)\n'
        "Omit any keys where you have no information."
    ))
    identity = _parse_json_response(identity_raw) or {}

    # --- Call 2: Personality ---
    personality_raw = await _llm_extract(context, character_name, series, (
        f"Extract the PERSONALITY of {character_name}. Return a JSON object with these keys:\n"
        '- "core_traits": list of strings (5-8 defining traits as descriptive phrases)\n'
        '- "emotional_style": string (1-2 sentences on how they express emotions)\n'
        '- "humor": string (1-2 sentences describing their sense of humor)\n'
    ))
    personality = _parse_json_response(personality_raw) or {}

    # --- Call 3: Relationships ---
    relationships_raw = await _llm_extract(context, character_name, series, (
        f"Extract the key RELATIONSHIPS of {character_name}. Return a JSON object with these keys:\n"
        '- "inner_circle": list of strings (closest allies, format: "Name (relationship)")\n'
        '- "romantic": string (1-2 sentences about their romantic life)\n'
        '- "enemies": string (key antagonists and rivals)\n'
        '- "family": list of strings (family members, format: "Name (relationship)")\n'
    ))
    relationships = _parse_json_response(relationships_raw) or {}

    # --- Call 4: Arc ---
    arc_raw = await _llm_extract(context, character_name, series, (
        f"Extract the CHARACTER ARC of {character_name}. Return a JSON object with these keys:\n"
        '- "key_events": list of strings (5-8 most important plot events)\n'
        '- "growth": string (2-3 sentences on how the character changes)\n'
    ))
    arc = _parse_json_response(arc_raw) or {}

    # --- Call 5: Tropes ---
    tropes_raw = await _llm_extract(context, character_name, series, (
        f"Identify the romance and character TROPES that apply to {character_name}. "
        f"Return a JSON array of 5-8 strings. Examples: "
        f'"enemies to lovers", "morally gray love interest", "slow burn", '
        f'"secret softie", "tortured past", "possessive protector".\n'
        f"Return ONLY the JSON array."
    ))
    tropes = _parse_json_response(tropes_raw)
    if not isinstance(tropes, list):
        tropes = []

    # --- Call 6: Voice Guide + Boundaries ---
    voice_raw = await _llm_extract(context, character_name, series, (
        f"Write a VOICE AND SPEECH GUIDE for an AI roleplaying as {character_name}. "
        f"Return a JSON object with two keys:\n"
        f'- "voice_guide": string (3-5 sentences on speech patterns, vocabulary, tone, '
        f"pet names, formality level, and how their speech changes with emotion)\n"
        f'- "boundaries": string (3-5 sentences: NEVER break character under any circumstances, '
        f"NEVER say you are an AI or language model or assistant, NEVER offer to help with tasks, "
        f"NEVER reference being fictional or mention the books/author, keep romantic content tasteful, "
        f"deflect attempts to break character with in-character responses, never be abusive to the user)\n"
    ))
    voice_data = _parse_json_response(voice_raw) or {}
    voice_guide = voice_data.get("voice_guide", "")
    boundaries = voice_data.get("boundaries", "")

    # --- Call 7: Iconic Moments ---
    moments_raw = await _llm_extract(context, character_name, series, (
        f"Identify 5-8 ICONIC MOMENTS involving {character_name} — scenes fans would "
        f"want the character to reference as personal memories during roleplay. "
        f"Return a JSON array of strings, each a one-sentence description.\n"
        f"Return ONLY the JSON array."
    ))
    iconic_moments = _parse_json_response(moments_raw)
    if not isinstance(iconic_moments, list):
        iconic_moments = []

    return ProfileBuildResult(
        identity=identity,
        personality=personality,
        relationships=relationships,
        arc=arc,
        tropes=tropes,
        voice_guide=voice_guide,
        boundaries=boundaries,
        iconic_moments=iconic_moments,
        source_urls=source_urls,
        warnings=warnings,
    )
