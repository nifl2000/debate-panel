"""
Multi-provider OpenAI-compatible LLM API Client

Provides async streaming and completion methods with retry logic.
"""

import os
import asyncio
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI


# Provider configuration
PROVIDERS = {
    "alibaba": {
        "base_url": "https://coding-intl.dashscope.aliyuncs.com/v1",
        "default_model": "qwen3-coder-next",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
    "custom": {
        "base_url": "",
        "default_model": "",
        "env_key": "LLM_API_KEY",
    },
}


class LLMError(Exception):
    """Base exception for LLM client errors."""

    pass


class LLMConfigurationError(LLMError):
    """Raised when configuration is invalid."""

    pass


class LLMAPIError(LLMError):
    """Raised when API call fails after all retries."""

    pass


class LLMClient:
    """
    Multi-provider OpenAI-compatible LLM client wrapper.

    Provides streaming and completion methods with automatic retry
    using exponential backoff.
    """

    def __init__(self, provider: str = "alibaba", model: str = "") -> None:
        """
        Initialize LLM client.

        Args:
            provider: Provider name (alibaba, openai, anthropic, groq, custom)
            model: Optional model override (defaults to provider default)

        Raises:
            LLMConfigurationError: If provider is not supported or API key missing
        """
        if provider not in PROVIDERS:
            raise LLMConfigurationError(
                f"Unknown provider: {provider}. Available: {list(PROVIDERS.keys())}"
            )

        self._provider = provider
        self._config = PROVIDERS[provider]

        env_key = self._config["env_key"]
        api_key = os.getenv(env_key)
        if not api_key:
            raise LLMConfigurationError(
                f"{env_key} environment variable not set"
            )
        if api_key == "your_api_key_here":
            raise LLMConfigurationError(f"{env_key} is set to placeholder value")

        base_url = self._config["base_url"]
        if provider == "custom":
            base_url = os.getenv("LLM_BASE_URL", base_url)
            if not base_url:
                raise LLMConfigurationError(
                    "LLM_BASE_URL environment variable not set for custom provider"
                )
            if not model:
                model = os.getenv("LLM_MODEL", "")
                if not model:
                    raise LLMConfigurationError(
                        "LLM_MODEL environment variable not set for custom provider"
                    )

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self._default_model = model if model else self._config["default_model"]

    @property
    def default_model(self) -> str:
        """Get default model for this provider."""
        return self._default_model

    async def _retry_with_backoff(
        self,
        func,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> Any:
        """
        Execute async function with exponential backoff retry.

        Args:
            func: Async function to execute
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay in seconds (doubles each retry)

        Returns:
            Result of the function call

        Raises:
            LLMAPIError: If all retries fail
        """
        last_exception = None

        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    await asyncio.sleep(delay)

        raise LLMAPIError(
            f"API call failed after {max_retries} attempts: {last_exception}"
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion response.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to provider's default)

        Yields:
            Content chunks as they arrive

        Raises:
            LLMAPIError: If API call fails after retries
        """
        model = model or self._default_model

        async def _create_stream():
            return await self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
            )

        # Retry the API call with backoff
        stream = await self._retry_with_backoff(_create_stream)

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
    ) -> str:
        """
        Get non-streaming chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to provider's default)

        Returns:
            Complete response content

        Raises:
            LLMAPIError: If API call fails after retries
        """
        model = model or self._default_model

        async def _complete():
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                stream=False,
            )

            if not response.choices or not response.choices[0].message.content:
                raise LLMAPIError("Empty response from API")

            return response.choices[0].message.content

        return await self._retry_with_backoff(_complete)

    async def close(self) -> None:
        """Close the underlying client."""
        await self._client.close()
