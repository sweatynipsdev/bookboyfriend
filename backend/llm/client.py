"""Claude API wrapper implementing the LLMProvider protocol."""

from anthropic import AsyncAnthropic

from backend.config import settings


class ClaudeLLMProvider:
    """LLM provider using the Anthropic Claude API.

    Satisfies the LLMProvider protocol via structural typing.
    """

    def __init__(self) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = "claude-sonnet-4-5-20250514"
        self._max_tokens = 1024

    async def chat(self, messages: list[dict], system: str = "") -> str:
        """Send messages to Claude and return the response text.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}.
            system: System prompt (Anthropic-specific parameter).

        Returns:
            The assistant's response text, or an error message on failure.
        """
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text
        except Exception as e:
            return f"Error communicating with Claude: {e}"
