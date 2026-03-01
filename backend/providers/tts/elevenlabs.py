"""ElevenLabs TTS provider using the REST API."""

import asyncio

import httpx

from backend.config import settings
from backend.providers.base import split_sentences

_ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsTTSProvider:
    """TTS provider using the ElevenLabs text-to-speech API.

    Satisfies the TTSProvider protocol via structural typing.
    """

    def __init__(self) -> None:
        self._api_key = settings.elevenlabs_api_key
        self._voice_id = settings.elevenlabs_voice_id
        self._max_retries = 3

    async def generate(self, text: str) -> bytes:
        """Generate MP3 audio from text.

        Splits into sentences, generates each, concatenates MP3 bytes.

        Args:
            text: The text to synthesize.

        Returns:
            MP3 audio bytes.
        """
        sentences = split_sentences(text)
        if not sentences:
            return b""

        audio_parts: list[bytes] = []
        for sentence in sentences:
            part = await self.generate_single(sentence)
            if part:
                audio_parts.append(part)

        return b"".join(audio_parts)

    async def generate_single(self, text: str) -> bytes:
        """Generate audio for a single sentence with retry logic."""
        url = f"{_ELEVENLABS_API_BASE}/text-to-speech/{self._voice_id}"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.content
            except (httpx.HTTPError, httpx.TimeoutException):
                if attempt == self._max_retries - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))
        return b""
