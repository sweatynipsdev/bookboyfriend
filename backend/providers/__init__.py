"""Provider factory — returns the correct provider based on config."""

from backend.config import settings
from backend.providers.base import LLMProvider, STTProvider, TTSProvider


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider."""
    if settings.llm_provider == "claude":
        from backend.llm.client import ClaudeLLMProvider

        return ClaudeLLMProvider()
    if settings.llm_provider == "minimax":
        from backend.llm.minimax import MiniMaxLLMProvider

        return MiniMaxLLMProvider()
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def get_stt_provider() -> STTProvider:
    """Return the configured STT provider (Phase 3)."""
    raise NotImplementedError(
        f"STT provider '{settings.stt_provider}' not yet implemented. Coming in Phase 3."
    )


def get_tts_provider() -> TTSProvider | None:
    """Return the configured TTS provider, or None if unavailable.

    Returns None (instead of raising) when no valid TTS configuration
    is found, enabling graceful text-only fallback.
    """
    if settings.tts_provider == "elevenlabs":
        if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
            return None
        from backend.providers.tts.elevenlabs import ElevenLabsTTSProvider

        return ElevenLabsTTSProvider()

    if settings.tts_provider == "minimax":
        if not settings.minimax_api_key or not settings.minimax_group_id:
            return None
        from backend.providers.tts.minimax_tts import MiniMaxTTSProvider

        return MiniMaxTTSProvider()

    return None
