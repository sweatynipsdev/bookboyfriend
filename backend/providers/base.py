"""Protocol definitions for all swappable providers.

Every inference layer (STT, TTS, LLM, Embedding) follows a Protocol interface.
Swapping providers is a config flag change, not a refactor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TranscriptResult:
    """Result from a speech-to-text transcription."""

    text: str
    confidence: float
    language: str


class STTProvider(Protocol):
    """Speech-to-text provider interface."""

    async def transcribe(
        self, audio: bytes, format: str = "webm"
    ) -> TranscriptResult: ...


class TTSProvider(Protocol):
    """Text-to-speech provider interface."""

    async def generate(self, text: str) -> bytes: ...
    async def generate_single(self, text: str) -> bytes: ...


def split_sentences(text: str) -> list[str]:
    """Split text into sentences for streaming TTS."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


class LLMProvider(Protocol):
    """Large language model provider interface."""

    async def chat(self, messages: list[dict]) -> str: ...


class EmbeddingProvider(Protocol):
    """Embedding model provider interface."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...
