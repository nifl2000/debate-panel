from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models import (
    Agent,
    AgentType,
    DiscussionConfig,
    DiscussionSession,
    DiscussionState,
    Message,
    MessageType,
)


class TestDiscussionState:
    def test_enum_values(self):
        assert DiscussionState.ACTIVE.value == "ACTIVE"
        assert DiscussionState.PAUSED.value == "PAUSED"
        assert DiscussionState.COMPLETED.value == "COMPLETED"
        assert DiscussionState.ERROR.value == "ERROR"


class TestDiscussionConfig:
    def test_default_values(self):
        config = DiscussionConfig()
        assert config.max_messages == 20
        assert config.language == "auto"
        assert config.model == "qwen3.6-plus"

    def test_custom_values(self):
        config = DiscussionConfig(max_messages=50, language="en", model="gpt-4")
        assert config.max_messages == 50
        assert config.language == "en"
        assert config.model == "gpt-4"

    def test_validation_max_messages_too_low(self):
        with pytest.raises(ValidationError):
            DiscussionConfig(max_messages=0)

    def test_validation_max_messages_too_high(self):
        with pytest.raises(ValidationError):
            DiscussionConfig(max_messages=101)

    def test_serialization(self):
        config = DiscussionConfig()
        data = config.model_dump()
        assert data["max_messages"] == 20
        assert data["language"] == "auto"
        assert data["model"] == "qwen3.6-plus"

    def test_deserialization(self):
        data = {"max_messages": 30, "language": "de", "model": "claude-3"}
        config = DiscussionConfig.model_validate(data)
        assert config.max_messages == 30
        assert config.language == "de"
        assert config.model == "claude-3"


class TestAgentType:
    def test_enum_values(self):
        assert AgentType.PERSONA.value == "PERSONA"
        assert AgentType.MODERATOR.value == "MODERATOR"
        assert AgentType.FACT_CHECKER.value == "FACT_CHECKER"


class TestAgent:
    def test_create_valid_agent(self):
        agent = Agent(
            id="123e4567-e89b-12d3-a456-426614174000",
            name="John Doe",
            role="Proponent",
            background="Expert in economics",
            stance="Supports the proposal",
            type=AgentType.PERSONA,
        )
        assert agent.id == "123e4567-e89b-12d3-a456-426614174000"
        assert agent.name == "John Doe"
        assert agent.role == "Proponent"
        assert agent.type == AgentType.PERSONA

    def test_serialization(self):
        agent = Agent(
            id="123e4567-e89b-12d3-a456-426614174000",
            name="Jane",
            role="Opponent",
            background="Legal expert",
            stance="Against the proposal",
            type=AgentType.PERSONA,
        )
        data = agent.model_dump()
        assert data["id"] == "123e4567-e89b-12d3-a456-426614174000"
        assert data["name"] == "Jane"
        assert data["type"] == "PERSONA"

    def test_deserialization(self):
        data = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Test Agent",
            "role": "Moderator",
            "background": "Background info",
            "stance": "Neutral",
            "type": "MODERATOR",
        }
        agent = Agent.model_validate(data)
        assert agent.id == "123e4567-e89b-12d3-a456-426614174000"
        assert agent.name == "Test Agent"
        assert agent.type == AgentType.MODERATOR


class TestMessageType:
    def test_enum_values(self):
        assert MessageType.AGENT.value == "AGENT"
        assert MessageType.FACT_CHECK.value == "FACT_CHECK"
        assert MessageType.MODERATOR.value == "MODERATOR"
        assert MessageType.SYSTEM.value == "SYSTEM"


class TestMessage:
    def test_create_valid_message(self):
        msg = Message(
            id="123e4567-e89b-12d3-a456-426614174001",
            agent_id="123e4567-e89b-12d3-a456-426614174000",
            content="This is a test message",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            type=MessageType.AGENT,
        )
        assert msg.id == "123e4567-e89b-12d3-a456-426614174001"
        assert msg.content == "This is a test message"
        assert msg.type == MessageType.AGENT

    def test_serialization(self):
        msg = Message(
            id="123e4567-e89b-12d3-a456-426614174001",
            agent_id="123e4567-e89b-12d3-a456-426614174000",
            content="Test",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            type=MessageType.AGENT,
        )
        data = msg.model_dump()
        assert data["id"] == "123e4567-e89b-12d3-a456-426614174001"
        assert data["type"] == "AGENT"

    def test_deserialization(self):
        data = {
            "id": "123e4567-e89b-12d3-a456-426614174001",
            "agent_id": "123e4567-e89b-12d3-a456-426614174000",
            "content": "Test message",
            "timestamp": "2024-01-01T12:00:00",
            "type": "FACT_CHECK",
        }
        msg = Message.model_validate(data)
        assert msg.id == "123e4567-e89b-12d3-a456-426614174001"
        assert msg.type == MessageType.FACT_CHECK


class TestDiscussionSession:
    def test_create_valid_session(self):
        session = DiscussionSession(
            id="123e4567-e89b-12d3-a456-426614174099",
            topic="Should AI be regulated?",
            state=DiscussionState.ACTIVE,
            conversation_log=[],
            agents=[],
            config=DiscussionConfig(),
        )
        assert session.id == "123e4567-e89b-12d3-a456-426614174099"
        assert session.topic == "Should AI be regulated?"
        assert session.state == DiscussionState.ACTIVE

    def test_session_with_agents_and_messages(self):
        agent = Agent(
            id="123e4567-e89b-12d3-a456-426614174000",
            name="John",
            role="Proponent",
            background="Expert",
            stance="Yes",
            type=AgentType.PERSONA,
        )
        msg = Message(
            id="123e4567-e89b-12d3-a456-426614174001",
            agent_id="123e4567-e89b-12d3-a456-426614174000",
            content="Hello",
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            type=MessageType.AGENT,
        )
        session = DiscussionSession(
            id="123e4567-e89b-12d3-a456-426614174099",
            topic="Test",
            state=DiscussionState.ACTIVE,
            conversation_log=[msg],
            agents=[agent],
            config=DiscussionConfig(),
        )
        assert len(session.agents) == 1
        assert len(session.conversation_log) == 1

    def test_serialization(self):
        session = DiscussionSession(
            id="123e4567-e89b-12d3-a456-426614174099",
            topic="Test",
            state=DiscussionState.ACTIVE,
            conversation_log=[],
            agents=[],
            config=DiscussionConfig(),
        )
        data = session.model_dump()
        assert data["id"] == "123e4567-e89b-12d3-a456-426614174099"
        assert data["state"] == "ACTIVE"

    def test_deserialization(self):
        data = {
            "id": "123e4567-e89b-12d3-a456-426614174099",
            "topic": "Test Topic",
            "state": "COMPLETED",
            "conversation_log": [],
            "agents": [],
            "config": {"max_messages": 30, "language": "en", "model": "test"},
        }
        session = DiscussionSession.model_validate(data)
        assert session.id == "123e4567-e89b-12d3-a456-426614174099"
        assert session.state == DiscussionState.COMPLETED
        assert session.config.max_messages == 30

    def test_state_enum_values(self):
        session = DiscussionSession(
            id="123e4567-e89b-12d3-a456-426614174099",
            topic="Test",
            state=DiscussionState.PAUSED,
            conversation_log=[],
            agents=[],
            config=DiscussionConfig(),
        )
        assert session.state == DiscussionState.PAUSED
        data = session.model_dump()
        assert data["state"] == "PAUSED"
