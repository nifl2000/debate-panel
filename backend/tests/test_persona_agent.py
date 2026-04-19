"""
Integration tests for PersonaAgent.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from app.agents.persona import PersonaAgent
from app.models.agent import AgentType
from app.models.message import MessageType
from app.orchestration.event_bus import EventBus, AgentMessageEvent
from app.llm.client import LLMAPIError


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.default_model = "qwen3.6-plus"

    async def mock_stream(messages):
        for chunk in ["Hello", " ", "from", " ", "persona!"]:
            yield chunk

    client.stream_chat = MagicMock(return_value=mock_stream([]))
    return client


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def mock_session(event_bus):
    session = MagicMock()
    session.topic = "Climate change policy"
    session.event_bus = event_bus
    return session


@pytest.fixture
def persona_agent(mock_llm_client, mock_session):
    return PersonaAgent(
        id="persona_1",
        name="Dr. Sarah Chen",
        role="Climate Scientist",
        background="PhD in Atmospheric Sciences, 15 years research experience",
        stance="Strongly supports aggressive climate action",
        llm_client=mock_llm_client,
        session=mock_session,
    )


@pytest.fixture
def persona_agent_no_session(mock_llm_client):
    return PersonaAgent(
        id="persona_2",
        name="John Smith",
        role="Policy Analyst",
        background="10 years in environmental policy",
        stance="Moderate approach preferred",
        llm_client=mock_llm_client,
        session=None,
    )


class TestPersonaAgentInitialization:
    def test_persona_agent_has_correct_attributes(self, persona_agent):
        assert persona_agent.id == "persona_1"
        assert persona_agent.name == "Dr. Sarah Chen"
        assert persona_agent.role == "Climate Scientist"
        assert (
            persona_agent.background
            == "PhD in Atmospheric Sciences, 15 years research experience"
        )
        assert persona_agent.stance == "Strongly supports aggressive climate action"
        assert persona_agent.type == AgentType.PERSONA

    def test_persona_agent_without_session(self, persona_agent_no_session):
        assert persona_agent_no_session.session is None
        assert persona_agent_no_session.stance == "Moderate approach preferred"


class TestStanceManagement:
    def test_stance_property_returns_current_stance(self, persona_agent):
        assert persona_agent.stance == "Strongly supports aggressive climate action"

    def test_update_stance_changes_stance(self, persona_agent):
        persona_agent.update_stance(
            "Now supports moderate action after seeing evidence"
        )
        assert (
            persona_agent.stance == "Now supports moderate action after seeing evidence"
        )

    def test_stance_can_be_updated_multiple_times(self, persona_agent):
        persona_agent.update_stance("First change")
        persona_agent.update_stance("Second change")
        assert persona_agent.stance == "Second change"


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_generate_response_returns_message(
        self, persona_agent, mock_llm_client
    ):
        async def mock_stream(messages):
            for chunk in ["I", " ", "believe", " ", "we", " ", "must", " ", "act", "."]:
                yield chunk

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        context = [{"role": "user", "content": "What is your position?"}]
        response = await persona_agent.generate_response(context)

        assert response.content == "I believe we must act."
        assert response.agent_id == "persona_1"
        assert response.type == MessageType.AGENT

    @pytest.mark.asyncio
    async def test_generate_response_uses_persona_prompt(
        self, persona_agent, mock_llm_client
    ):
        captured_messages = None

        async def mock_stream(messages):
            captured_messages = messages
            yield "Response"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        context = [{"role": "user", "content": "Question"}]
        await persona_agent.generate_response(context)

        mock_llm_client.stream_chat.assert_called_once()
        call_args = mock_llm_client.stream_chat.call_args[0][0]
        assert call_args[0]["role"] == "system"
        assert "Dr. Sarah Chen" in call_args[0]["content"]
        assert "Climate Scientist" in call_args[0]["content"]
        assert "Strongly supports aggressive climate action" in call_args[0]["content"]
        assert "Climate change policy" in call_args[0]["content"]

    @pytest.mark.asyncio
    async def test_generate_response_without_session(
        self, persona_agent_no_session, mock_llm_client
    ):
        async def mock_stream(messages):
            yield "This is a valid response that is long enough"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        context = [{"role": "user", "content": "Question"}]
        response = await persona_agent_no_session.generate_response(context)

        assert response.content == "This is a valid response that is long enough"
        assert response.agent_id == "persona_2"

        call_args = mock_llm_client.stream_chat.call_args[0][0]
        assert "Unknown topic" in call_args[0]["content"]


class TestEventPublishing:
    @pytest.mark.asyncio
    async def test_event_published_to_bus(
        self, persona_agent, mock_llm_client, event_bus
    ):
        async def mock_stream(messages):
            yield "Test response content"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        events_received = []
        event_bus.subscribe("agent_message", lambda e: events_received.append(e))

        context = [{"role": "user", "content": "Question"}]
        await persona_agent.generate_response(context)

        assert len(events_received) == 1
        event = events_received[0]
        assert isinstance(event, AgentMessageEvent)
        assert event.agent_id == "persona_1"
        assert event.agent_type == AgentType.PERSONA.value
        assert event.content == "Test response content"
        assert event.metadata["persona_name"] == "Dr. Sarah Chen"
        assert event.metadata["persona_role"] == "Climate Scientist"
        assert (
            event.metadata["current_stance"]
            == "Strongly supports aggressive climate action"
        )

    @pytest.mark.asyncio
    async def test_no_event_published_without_session(
        self, persona_agent_no_session, mock_llm_client
    ):
        async def mock_stream(messages):
            yield "This is a valid response that is long enough"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        context = [{"role": "user", "content": "Question"}]
        response = await persona_agent_no_session.generate_response(context)

        assert response.content == "This is a valid response that is long enough"


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_llm_error_propagates(self, persona_agent, mock_llm_client):
        async def mock_stream_error(messages):
            raise LLMAPIError("API call failed")
            yield ""

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream_error([]))

        context = [{"role": "user", "content": "Question"}]

        with pytest.raises(LLMAPIError):
            await persona_agent.generate_response(context)


class TestToAgentModel:
    def test_to_agent_model_returns_correct_model(self, persona_agent):
        agent_model = persona_agent.to_agent_model()

        assert agent_model.id == "persona_1"
        assert agent_model.name == "Dr. Sarah Chen"
        assert agent_model.role == "Climate Scientist"
        assert (
            agent_model.background
            == "PhD in Atmospheric Sciences, 15 years research experience"
        )
        assert agent_model.stance == "Strongly supports aggressive climate action"
        assert agent_model.type == AgentType.PERSONA

    def test_to_agent_model_reflects_stance_changes(self, persona_agent):
        persona_agent.update_stance("New stance after discussion")
        agent_model = persona_agent.to_agent_model()

        assert agent_model.stance == "New stance after discussion"


class TestStanceAdaptationIntegration:
    @pytest.mark.asyncio
    async def test_stance_can_change_after_response(
        self, persona_agent, mock_llm_client
    ):
        async def mock_stream(messages):
            yield "After reviewing the evidence, I now support a more balanced approach."

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        context = [{"role": "user", "content": "What do you think now?"}]
        await persona_agent.generate_response(context)

        persona_agent.update_stance("More balanced approach after reviewing evidence")

        assert persona_agent.stance == "More balanced approach after reviewing evidence"
        assert (
            persona_agent.to_agent_model().stance
            == "More balanced approach after reviewing evidence"
        )
