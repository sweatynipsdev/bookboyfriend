"""MiniMax TTS provider using the native t2a_v2 REST API."""

import asyncio

import httpx

from backend.config import settings
from backend.providers.base import split_sentences


class MiniMaxTTSProvider:
    """TTS provider using MiniMax's native Speech API (t2a_v2).

    Satisfies the TTSProvider protocol via structural typing.
    Uses the MiniMax REST endpoint (NOT OpenAI-compatible).
    """

    def __init__(self) -> None:
        self._api_key = settings.minimax_api_key
        self._group_id = settings.minimax_group_id
        self._model = settings.minimax_tts_model
        self._voice = settings.minimax_tts_voice
        self._max_retries = 3
        self._base_url = "https://api.minimax.io/v1"

    async def generate(self, text: str) -> bytes:
        """Generate MP3 audio from text in a single API call.

        Args:
            text: The text to synthesize.

        Returns:
            MP3 audio bytes.
        """
        if not text.strip():
            return b""
        return await self.generate_single(text)

    async def generate_single(self, text: str) -> bytes:
        """Generate audio for a single sentence with retry logic."""
        url = f"{self._base_url}/t2a_v2?GroupId={self._group_id}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": self._voice,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "format": "mp3",
                "sample_rate": 32000,
                "bitrate": 128000,
                "channel": 1,
            },
        }

        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()

                    data = response.json()

                    # Check for API-level errors
                    base_resp = data.get("base_resp", {})
                    if base_resp.get("status_code", 0) != 0:
                        raise RuntimeError(
                            f"MiniMax TTS error: {base_resp.get('status_msg', 'unknown')}"
                        )

                    # Audio is hex-encoded in the response
                    hex_audio = data.get("data", {}).get("audio", "")
                    if not hex_audio:
                        raise RuntimeError("No audio data in MiniMax TTS response")

                    return bytes.fromhex(hex_audio)

            except Exception:
                if attempt == self._max_retries - 1:
                    raise
                await asyncio.sleep(1 * (attempt + 1))

        return b""
