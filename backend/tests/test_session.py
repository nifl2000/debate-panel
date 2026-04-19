"""
Integration tests for DiscussionSession class.

Tests cover:
- Session lifecycle (start → pause → stop)
- Concurrent message addition (no race conditions)
- Context windowing works correctly
- Event publishing on message add
"""

import asyncio
from datetime import datetime

import pytest
from datetime import datetime
from unittest.mock import Mock

from app.models.discussion import DiscussionConfig, DiscussionState
from app.models.message import Message, MessageType
from app.orchestration.event_bus import EventBus, AgentMessageEvent
from app.orchestration.session import DiscussionSession


@pytest.fixture
def event_bus():
    """Create an EventBus instance for testing."""
    return EventBus()


@pytest.fixture
def session(event_bus):
    """Create a DiscussionSession instance for testing."""
    return DiscussionSession(
        topic="Climate change solutions",
        event_bus=event_bus,
        config=DiscussionConfig(max_messages=20),
    )


@pytest.fixture
def sample_message():
    """Create a sample Message instance for testing."""
    return Message(
        id="msg_test_001",
        agent_id="agent_001",
        content="We should invest more in renewable energy.",
        timestamp=datetime.now(),
        type=MessageType.AGENT,
    )


class TestSessionLifecycle:
    """Tests for session lifecycle management."""

    def test_session_initialization(self, session):
        """Test that session initializes with correct default values."""
        assert session.topic == "Climate change solutions"
        assert session.state == DiscussionState.PAUSED
        assert len(session.conversation_log) == 0
        assert len(session.agents) == 0
        assert session.config.max_messages == 20
        assert session._marked_for_cleanup is False

    def test_session_has_unique_id(self, event_bus):
        """Test that each session gets a unique ID."""
        session1 = DiscussionSession(topic="Topic 1", event_bus=event_bus)
        session2 = DiscussionSession(topic="Topic 2", event_bus=event_bus)
        assert session1.id != session2.id

    def test_session_custom_id(self, event_bus):
        """Test that session can have a custom ID."""
        custom_id = "custom_session_123"
        session = DiscussionSession(
            topic="Topic", event_bus=event_bus, session_id=custom_id
        )
        assert session.id == custom_id

    def test_start_discussion(self, session):
        """Test starting a discussion sets state to ACTIVE."""
        session.start_discussion()
        assert session.state == DiscussionState.ACTIVE

    def test_pause_discussion(self, session):
        """Test pausing a discussion sets state to PAUSED."""
        session.start_discussion()
        session.pause_discussion()
        assert session.state == DiscussionState.PAUSED

    def test_stop_discussion(self, session):
        """Test stopping a discussion sets state to COMPLETED."""
        session.start_discussion()
        session.stop_discussion()
        assert session.state == DiscussionState.COMPLETED

    def test_full_lifecycle(self, session):
        """Test full lifecycle: start → pause → stop."""
        assert session.state == DiscussionState.PAUSED

        session.start_discussion()
        assert session.state == DiscussionState.ACTIVE

        session.pause_discussion()
        assert session.state == DiscussionState.PAUSED

        session.start_discussion()
        assert session.state == DiscussionState.ACTIVE

        session.stop_discussion()
        assert session.state == DiscussionState.COMPLETED

    def test_cleanup_marks_session(self, session):
        """Test cleanup marks session for deletion."""
        session.cleanup()
        assert session.is_marked_for_cleanup() is True
        assert session.state == DiscussionState.COMPLETED


class TestMessageAddition:
    """Tests for message addition and event publishing."""

    @pytest.mark.asyncio
    async def test_add_message_appends_to_log(self, session, sample_message):
        """Test that add_message appends message to conversation log."""
        await session.add_message(sample_message)
        assert len(session.conversation_log) == 1
        assert session.conversation_log[0] == sample_message

    @pytest.mark.asyncio
    async def test_add_multiple_messages(self, session):
        """Test adding multiple messages to conversation log."""
        for i in range(5):
            msg = Message(
                id=f"msg_{i}",
                agent_id="agent_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        assert len(session.conversation_log) == 5

    @pytest.mark.asyncio
    async def test_add_message_publishes_event(self, session, sample_message):
        """Test that add_message publishes AgentMessageEvent."""
        received_events = []

        def handler(event):
            received_events.append(event)

        session.event_bus.subscribe("agent_message", handler)
        await session.add_message(sample_message)

        assert len(received_events) == 1
        assert isinstance(received_events[0], AgentMessageEvent)
        assert received_events[0].agent_id == sample_message.agent_id
        assert received_events[0].content == sample_message.content

    @pytest.mark.asyncio
    async def test_add_message_updates_last_activity(self, session, sample_message):
        """Test that add_message updates last activity timestamp."""
        initial_activity = session.get_last_activity()
        await session.add_message(sample_message)
        new_activity = session.get_last_activity()
        assert new_activity >= initial_activity


class TestConcurrentAccess:
    """Tests for concurrent message addition (thread safety)."""

    @pytest.mark.asyncio
    async def test_concurrent_message_addition(self, session):
        """Test that concurrent message additions don't cause race conditions."""
        num_messages = 100

        async def add_message_task(i):
            msg = Message(
                id=f"msg_concurrent_{i}",
                agent_id="agent_001",
                content=f"Concurrent message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        tasks = [add_message_task(i) for i in range(num_messages)]
        await asyncio.gather(*tasks)

        assert len(session.conversation_log) == num_messages

        message_ids = [msg.id for msg in session.conversation_log]
        assert len(set(message_ids)) == num_messages

    @pytest.mark.asyncio
    async def test_concurrent_add_and_read(self, session):
        """Test that reading while adding doesn't cause issues."""
        num_adds = 50
        read_counts = []

        async def add_messages():
            for i in range(num_adds):
                msg = Message(
                    id=f"msg_read_test_{i}",
                    agent_id="agent_001",
                    content=f"Message {i}",
                    timestamp=datetime.now(),
                    type=MessageType.AGENT,
                )
                await session.add_message(msg)

        async def read_counts_task():
            for _ in range(num_adds):
                read_counts.append(session.get_message_count())
                await asyncio.sleep(0.001)

        await asyncio.gather(add_messages(), read_counts_task())

        assert session.get_message_count() == num_adds


class TestContextWindowing:
    """Tests for context windowing functionality."""

    @pytest.mark.asyncio
    async def test_get_context_empty_log(self, session):
        """Test that get_context_for_agent returns empty list for empty log."""
        context = session.get_context_for_agent("agent_001")
        assert context == []

    @pytest.mark.asyncio
    async def test_get_context_single_message(self, session, sample_message):
        """Test that get_context_for_agent returns correct format for single message."""
        await session.add_message(sample_message)
        context = session.get_context_for_agent("agent_001")

        assert len(context) == 1
        assert context[0]["role"] == "assistant"
        assert sample_message.content in context[0]["content"]

    @pytest.mark.asyncio
    async def test_get_context_role_assignment(self, session):
        """Test that role is correctly assigned based on agent_id."""
        msg1 = Message(
            id="msg_1",
            agent_id="agent_001",
            content="Message from agent 001",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        msg2 = Message(
            id="msg_2",
            agent_id="agent_002",
            content="Message from agent 002",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )

        await session.add_message(msg1)
        await session.add_message(msg2)

        context_for_agent1 = session.get_context_for_agent("agent_001")
        assert context_for_agent1[0]["role"] == "assistant"
        assert context_for_agent1[1]["role"] == "user"

        context_for_agent2 = session.get_context_for_agent("agent_002")
        assert context_for_agent2[0]["role"] == "user"
        assert context_for_agent2[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_get_context_windowing_large_log(self, session):
        """Test that context windowing works for large conversation logs."""
        for i in range(100):
            msg = Message(
                id=f"msg_large_{i}",
                agent_id="agent_001",
                content=f"This is a longer message number {i} with more content to increase token count.",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        context = session.get_context_for_agent("agent_001", max_tokens=1000)
        assert len(context) < 100

    @pytest.mark.asyncio
    async def test_get_context_preserves_order(self, session):
        """Test that context windowing preserves message order."""
        for i in range(10):
            msg = Message(
                id=f"msg_order_{i}",
                agent_id="agent_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        context = session.get_context_for_agent("agent_001")
        for i, ctx in enumerate(context):
            assert f"Message {i}" in ctx["content"]


class TestAgentManagement:
    """Tests for agent management in session."""

    def test_add_agent(self, session):
        """Test adding an agent to the session."""
        from app.agents.base import BaseAgent
        from app.models.agent import AgentType

        class MockAgent(BaseAgent):
            async def generate_response(self, context):
                return Message(
                    id="mock_msg",
                    agent_id=self.id,
                    content="Mock response",
                    timestamp=datetime.now(),
                    type=MessageType.AGENT,
                )

        mock_llm = Mock()
        agent = MockAgent(
            id="agent_001",
            name="Test Agent",
            type=AgentType.PERSONA,
            llm_client=mock_llm,
        )
        session.add_agent(agent)

        assert "agent_001" in session.agents
        assert session.agents["agent_001"] == agent

    def test_remove_agent(self, session):
        """Test removing an agent from the session."""
        from app.agents.base import BaseAgent
        from app.models.agent import AgentType

        class MockAgent(BaseAgent):
            async def generate_response(self, context):
                return Message(
                    id="mock_msg",
                    agent_id=self.id,
                    content="Mock response",
                    timestamp=datetime.now(),
                    type=MessageType.AGENT,
                )

        mock_llm = Mock()
        agent = MockAgent(
            id="agent_001",
            name="Test Agent",
            type=AgentType.PERSONA,
            llm_client=mock_llm,
        )
        session.add_agent(agent)
        session.remove_agent("agent_001")

        assert "agent_001" not in session.agents

    def test_remove_nonexistent_agent(self, session):
        """Test removing an agent that doesn't exist."""
        session.remove_agent("nonexistent_agent")
        assert len(session.agents) == 0


class TestMessageLimit:
    """Tests for message limit checking."""

    @pytest.mark.asyncio
    async def test_is_within_message_limit_true(self, session):
        """Test that is_within_message_limit returns True when under limit."""
        for i in range(10):
            msg = Message(
                id=f"msg_limit_{i}",
                agent_id="agent_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        assert session.is_within_message_limit() is True

    @pytest.mark.asyncio
    async def test_is_within_message_limit_false(self, session):
        """Test that is_within_message_limit returns False when at limit."""
        session.config = DiscussionConfig(max_messages=5)

        for i in range(5):
            msg = Message(
                id=f"msg_at_limit_{i}",
                agent_id="agent_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        assert session.is_within_message_limit() is False

    def test_get_message_count(self, session):
        """Test that get_message_count returns correct count."""
        assert session.get_message_count() == 0


class TestPydanticConversion:
    """Tests for conversion to Pydantic model."""

    @pytest.mark.asyncio
    async def test_to_pydantic_model(self, session, sample_message):
        """Test conversion to Pydantic model."""
        await session.add_message(sample_message)
        session.start_discussion()

        pydantic_model = session.to_pydantic_model()

        assert pydantic_model.id == session.id
        assert pydantic_model.topic == session.topic
        assert pydantic_model.state == DiscussionState.ACTIVE
        assert len(pydantic_model.conversation_log) == 1
        assert pydantic_model.config.max_messages == 20
