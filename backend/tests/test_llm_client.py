"""Unit tests for LLM client wrapper."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.llm.client import (
    LLMClient,
    LLMError,
    LLMConfigurationError,
    LLMAPIError,
    PROVIDERS,
)


@pytest.fixture
def mock_env_api_key(monkeypatch):
    """Set mock API key in environment."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test_api_key_12345")


class TestProvidersConfig:
    """Test provider configuration."""

    def test_alibaba_provider_config(self):
        """Verify Alibaba provider has correct config."""
        assert "alibaba" in PROVIDERS
        assert (
            PROVIDERS["alibaba"]["base_url"]
            == "https://coding-intl.dashscope.aliyuncs.com/v1"
        )
        assert PROVIDERS["alibaba"]["default_model"] == "qwen3-coder-next"


class TestLLMClientInit:
    """Test LLM client initialization."""

    def test_init_success(self, mock_env_api_key):
        """Test successful client initialization."""
        client = LLMClient(provider="alibaba")
        assert client.default_model == "qwen3-coder-next"

    def test_init_unknown_provider(self, mock_env_api_key):
        """Test initialization with unknown provider raises error."""
        with pytest.raises(LLMConfigurationError) as exc_info:
            LLMClient(provider="unknown")
        assert "Unknown provider" in str(exc_info.value)

    def test_init_missing_api_key(self, monkeypatch):
        """Test initialization without API key raises error."""
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        with pytest.raises(LLMConfigurationError) as exc_info:
            LLMClient(provider="alibaba")
        assert "DASHSCOPE_API_KEY" in str(exc_info.value)

    def test_init_placeholder_api_key(self, monkeypatch):
        """Test initialization with placeholder API key raises error."""
        monkeypatch.setenv("DASHSCOPE_API_KEY", "your_api_key_here")
        with pytest.raises(LLMConfigurationError) as exc_info:
            LLMClient(provider="alibaba")
        assert "placeholder" in str(exc_info.value)


class MockAsyncStream:
    """Mock async iterator for streaming responses."""

    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        return self.chunks.pop(0)


class TestLLMClientStream:
    """Test streaming chat functionality."""

    @pytest.mark.asyncio
    async def test_stream_chat_success(self, mock_env_api_key):
        """Test successful streaming response."""
        client = LLMClient(provider="alibaba")

        mock_chunk_1 = MagicMock()
        mock_chunk_1.choices = [MagicMock(delta=MagicMock(content="Hello "))]

        mock_chunk_2 = MagicMock()
        mock_chunk_2.choices = [MagicMock(delta=MagicMock(content="world!"))]

        mock_stream = MockAsyncStream([mock_chunk_1, mock_chunk_2])

        mock_create = AsyncMock(return_value=mock_stream)
        client._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "Say hello"}]
        chunks = [chunk async for chunk in client.stream_chat(messages)]

        assert chunks == ["Hello ", "world!"]
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "qwen3-coder-next"
        assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_stream_chat_custom_model(self, mock_env_api_key):
        """Test streaming with custom model."""
        client = LLMClient(provider="alibaba")

        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="Response"))]

        mock_stream = MockAsyncStream([mock_chunk])

        mock_create = AsyncMock(return_value=mock_stream)
        client._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "Test"}]
        chunks = [
            chunk async for chunk in client.stream_chat(messages, model="custom-model")
        ]

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "custom-model"

    @pytest.mark.asyncio
    async def test_stream_chat_retry_on_error(self, mock_env_api_key):
        """Test streaming retries on API error."""
        client = LLMClient(provider="alibaba")

        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock(delta=MagicMock(content="Success"))]

        mock_stream = MockAsyncStream([mock_chunk])

        mock_create = AsyncMock(
            side_effect=[
                Exception("API Error 1"),
                Exception("API Error 2"),
                mock_stream,
            ]
        )
        client._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "Test"}]
        chunks = [chunk async for chunk in client.stream_chat(messages)]

        assert chunks == ["Success"]
        assert mock_create.call_count == 3


class TestLLMClientComplete:
    """Test non-streaming completion functionality."""

    @pytest.mark.asyncio
    async def test_complete_success(self, mock_env_api_key):
        """Test successful completion."""
        client = LLMClient(provider="alibaba")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]

        mock_create = AsyncMock(return_value=mock_response)
        client._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "Hello"}]
        result = await client.complete(messages)

        assert result == "Test response"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "qwen3-coder-next"
        assert call_kwargs["stream"] is False

    @pytest.mark.asyncio
    async def test_complete_empty_response(self, mock_env_api_key):
        """Test completion with empty response raises error."""
        client = LLMClient(provider="alibaba")

        mock_response = MagicMock()
        mock_response.choices = []

        mock_create = AsyncMock(return_value=mock_response)
        client._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(LLMAPIError) as exc_info:
            await client.complete(messages)
        assert "Empty response" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_complete_retry_on_error(self, mock_env_api_key):
        """Test completion retries on API error."""
        client = LLMClient(provider="alibaba")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Success"))]

        mock_create = AsyncMock(
            side_effect=[
                Exception("API Error 1"),
                Exception("API Error 2"),
                mock_response,
            ]
        )
        client._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "Test"}]
        result = await client.complete(messages)

        assert result == "Success"
        assert mock_create.call_count == 3


class TestLLMClientClose:
    """Test client cleanup."""

    @pytest.mark.asyncio
    async def test_close(self, mock_env_api_key):
        """Test close method calls underlying client close."""
        client = LLMClient(provider="alibaba")
        client._client.close = AsyncMock()

        await client.close()

        client._client.close.assert_called_once()


class TestLLMErrors:
    """Test custom exception classes."""

    def test_llm_error_base(self):
        """Test LLMError is base exception."""
        with pytest.raises(LLMError):
            raise LLMError("test")

    def test_llm_configuration_error(self):
        """Test LLMConfigurationError."""
        with pytest.raises(LLMConfigurationError):
            raise LLMConfigurationError("config error")

    def test_llm_api_error(self):
        """Test LLMAPIError."""
        with pytest.raises(LLMAPIError):
            raise LLMAPIError("api error")
