"""MiniMax API wrapper implementing the LLMProvider protocol.

Uses the OpenAI-compatible API at https://api.minimax.io/v1.
"""

import re

from openai import AsyncOpenAI

from backend.config import settings

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.DOTALL)


class MiniMaxLLMProvider:
    """LLM provider using the MiniMax API (OpenAI-compatible).

    Satisfies the LLMProvider protocol via structural typing.
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.minimax_api_key,
            base_url="https://api.minimax.io/v1",
        )
        self._model = settings.minimax_model
        self._max_tokens = 1024

    async def chat(self, messages: list[dict], system: str = "") -> str:
        """Send messages to MiniMax and return the response text.

        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}.
            system: System prompt (injected as a system message).

        Returns:
            The assistant's response text, or an error message on failure.
        """
        try:
            # OpenAI-compatible API uses system message in the messages list
            full_messages = []
            if system:
                full_messages.append({"role": "system", "content": system})
            full_messages.extend(messages)

            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=full_messages,
            )
            text = response.choices[0].message.content
            # MiniMax M2.5 wraps reasoning in <think>...</think> tags — strip them
            return _THINK_RE.sub("", text).strip()
        except Exception as e:
            return f"Error communicating with MiniMax: {e}"
