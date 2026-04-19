"""
Unit tests for BaseAgent abstract class.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.agents.base import BaseAgent
from app.models.agent import AgentType
from app.models.message import MessageType


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    async def generate_response(self, context):
        return self._create_message("Test response", MessageType.AGENT)


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.default_model = "qwen3.6-plus"
    return client


@pytest.fixture
def concrete_agent(mock_llm_client):
    return ConcreteAgent(
        id="test_agent_1",
        name="Test Agent",
        type=AgentType.PERSONA,
        llm_client=mock_llm_client,
    )


class TestBaseAgentCannotInstantiateDirectly:
    def test_cannot_instantiate_base_agent(self, mock_llm_client):
        with pytest.raises(TypeError):
            BaseAgent(
                id="test",
                name="Test",
                type=AgentType.PERSONA,
                llm_client=mock_llm_client,
            )


class TestConcreteSubclass:
    @pytest.mark.asyncio
    async def test_concrete_subclass_can_instantiate(self, concrete_agent):
        assert concrete_agent.id == "test_agent_1"
        assert concrete_agent.name == "Test Agent"
        assert concrete_agent.type == AgentType.PERSONA

    @pytest.mark.asyncio
    async def test_concrete_subclass_can_generate_response(self, concrete_agent):
        context = [{"role": "user", "content": "Hello"}]
        response = await concrete_agent.generate_response(context)
        assert response.content == "Test response"
        assert response.agent_id == "test_agent_1"
        assert response.type == MessageType.AGENT


class TestContextWindowing:
    def test_empty_messages_returns_empty(self, concrete_agent):
        result = concrete_agent._get_context_window([])
        assert result == []

    def test_small_messages_returns_all(self, concrete_agent):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = concrete_agent._get_context_window(messages, max_tokens=10000)
        assert len(result) == 2

    def test_windowing_respects_token_limit(self, concrete_agent):
        messages = [
            {"role": "user", "content": "Short message"},
            {"role": "assistant", "content": "Another short message"},
            {"role": "user", "content": "Third message"},
        ]
        result = concrete_agent._get_context_window(messages, max_tokens=50)
        assert len(result) >= 1
        assert result[-1]["content"] == "Third message"


class TestMessageFormatting:
    def test_format_messages_adds_system_prompt(self, concrete_agent):
        context = [{"role": "user", "content": "Hello"}]
        system_prompt = "You are a helpful assistant."
        result = concrete_agent._format_messages_for_llm(context, system_prompt)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == system_prompt
        assert result[1]["content"] == "Hello"

    def test_format_messages_preserves_context(self, concrete_agent):
        context = [
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer."},
        ]
        system_prompt = "System prompt"
        result = concrete_agent._format_messages_for_llm(context, system_prompt)
        assert len(result) == 3
        assert result[1]["content"] == "Question?"
        assert result[2]["content"] == "Answer."


class TestCreateMessage:
    def test_create_message_generates_unique_id(self, concrete_agent):
        import time

        msg1 = concrete_agent._create_message("Content 1", MessageType.AGENT)
        time.sleep(0.001)
        msg2 = concrete_agent._create_message("Content 2", MessageType.AGENT)
        assert msg1.id != msg2.id

    def test_create_message_sets_agent_id(self, concrete_agent):
        msg = concrete_agent._create_message("Test", MessageType.AGENT)
        assert msg.agent_id == "test_agent_1"

    def test_create_message_sets_correct_type(self, concrete_agent):
        msg = concrete_agent._create_message("Test", MessageType.FACT_CHECK)
        assert msg.type == MessageType.FACT_CHECK

    def test_create_message_has_timestamp(self, concrete_agent):
        msg = concrete_agent._create_message("Test", MessageType.AGENT)
        assert msg.timestamp is not None
