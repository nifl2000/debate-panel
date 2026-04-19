import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.dependencies import get_session_store, _session_store, get_llm_client
from app.orchestration.session import DiscussionSession
from app.orchestration.event_bus import EventBus
from app.models.discussion import DiscussionConfig, DiscussionState
from app.models.message import Message, MessageType


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def clear_session_store():
    _session_store.clear()
    yield
    _session_store.clear()


@pytest.fixture
def sample_session():
    event_bus = EventBus()
    config = DiscussionConfig()
    session = DiscussionSession(
        topic="Climate Change Policy",
        event_bus=event_bus,
        config=config,
        session_id="test-session-123",
    )
    session.state = DiscussionState.COMPLETED

    agent1 = MagicMock()
    agent1.name = "Dr. Sarah Chen"
    agent1.type = "PERSONA"
    session.agents["agent_1"] = agent1

    agent2 = MagicMock()
    agent2.name = "John Martinez"
    agent2.type = "PERSONA"
    session.agents["agent_2"] = agent2

    moderator = MagicMock()
    moderator.name = "Discussion Moderator"
    moderator.type = "MODERATOR"
    session.agents["moderator_001"] = moderator

    msg1 = Message(
        id="msg_1",
        agent_id="agent_1",
        content="We need urgent action on climate change.",
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        type=MessageType.AGENT,
    )
    msg2 = Message(
        id="msg_2",
        agent_id="agent_2",
        content="I disagree. Market solutions are better than regulation.",
        timestamp=datetime(2024, 1, 15, 10, 5, 0),
        type=MessageType.AGENT,
    )
    msg3 = Message(
        id="msg_3",
        agent_id="moderator_001",
        content="Let's focus on the economic impacts.",
        timestamp=datetime(2024, 1, 15, 10, 10, 0),
        type=MessageType.MODERATOR,
    )

    session.conversation_log.extend([msg1, msg2, msg3])

    return session


class TestTextExport:
    @pytest.mark.asyncio
    async def test_text_export_success(self, client, sample_session):
        store = get_session_store()
        store[sample_session.id] = sample_session

        response = await client.get(
            f"/api/discussion/{sample_session.id}/export?format=TEXT"
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert ".txt" in response.headers["content-disposition"]

        content = response.text
        assert "Climate Change Policy" in content
        assert "Dr. Sarah Chen" in content
        assert "John Martinez" in content
        assert "We need urgent action on climate change." in content
        assert "Market solutions are better than regulation." in content

    @pytest.mark.asyncio
    async def test_text_export_default_format(self, client, sample_session):
        store = get_session_store()
        store[sample_session.id] = sample_session

        response = await client.get(f"/api/discussion/{sample_session.id}/export")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"


class TestMarkdownExport:
    @pytest.mark.asyncio
    async def test_markdown_export_success(self, client, sample_session):
        store = get_session_store()
        store[sample_session.id] = sample_session

        response = await client.get(
            f"/api/discussion/{sample_session.id}/export?format=MARKDOWN"
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert ".md" in response.headers["content-disposition"]

        content = response.text
        assert "# Discussion: Climate Change Policy" in content
        assert "## Participants" in content
        assert "## Conversation" in content
        assert "Dr. Sarah Chen" in content
        assert "John Martinez" in content
        assert "We need urgent action on climate change." in content

    @pytest.mark.asyncio
    async def test_markdown_structure(self, client, sample_session):
        store = get_session_store()
        store[sample_session.id] = sample_session

        response = await client.get(
            f"/api/discussion/{sample_session.id}/export?format=MARKDOWN"
        )

        content = response.text
        assert "### [" in content
        assert "Moderator:" in content
        assert "---" in content


class TestPDFExport:
    @pytest.mark.asyncio
    async def test_pdf_export_returns_501(self, client, sample_session):
        store = get_session_store()
        store[sample_session.id] = sample_session

        response = await client.get(
            f"/api/discussion/{sample_session.id}/export?format=PDF"
        )

        assert response.status_code == 501
        assert "not implemented" in response.json()["detail"].lower()


class TestExportErrors:
    @pytest.mark.asyncio
    async def test_export_nonexistent_session(self, client):
        response = await client.get("/api/discussion/non-existent-id/export")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_export_nonexistent_session_with_format(self, client):
        response = await client.get(
            "/api/discussion/non-existent-id/export?format=TEXT"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_nonexistent_session_markdown(self, client):
        response = await client.get(
            "/api/discussion/non-existent-id/export?format=MARKDOWN"
        )

        assert response.status_code == 404


class TestExportEdgeCases:
    @pytest.mark.asyncio
    async def test_export_empty_conversation(self, client):
        event_bus = EventBus()
        config = DiscussionConfig()
        session = DiscussionSession(
            topic="Empty Discussion",
            event_bus=event_bus,
            config=config,
            session_id="empty-session",
        )
        session.state = DiscussionState.ACTIVE

        agent = MagicMock()
        agent.name = "Test Agent"
        agent.type = "PERSONA"
        session.agents["agent_1"] = agent

        store = get_session_store()
        store[session.id] = session

        response = await client.get(f"/api/discussion/{session.id}/export?format=TEXT")

        assert response.status_code == 200
        content = response.text
        assert "Empty Discussion" in content
        assert "ACTIVE" in content

    @pytest.mark.asyncio
    async def test_export_with_fact_check_message(self, client):
        event_bus = EventBus()
        config = DiscussionConfig()
        session = DiscussionSession(
            topic="Fact Check Test",
            event_bus=event_bus,
            config=config,
            session_id="fact-check-session",
        )
        session.state = DiscussionState.COMPLETED

        agent = MagicMock()
        agent.name = "Fact Checker"
        agent.type = "FACT_CHECKER"
        session.agents["fact_checker_001"] = agent

        msg = Message(
            id="msg_1",
            agent_id="fact_checker_001",
            content="Claim verified: Temperatures have risen.",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.FACT_CHECK,
        )
        session.conversation_log.append(msg)

        store = get_session_store()
        store[session.id] = session

        response = await client.get(
            f"/api/discussion/{session.id}/export?format=MARKDOWN"
        )

        assert response.status_code == 200
        content = response.text
        assert "Fact Check:" in content
        assert "Claim verified" in content

    @pytest.mark.asyncio
    async def test_export_session_isolation(self, client):
        event_bus1 = EventBus()
        event_bus2 = EventBus()
        config = DiscussionConfig()

        session1 = DiscussionSession(
            topic="Session One",
            event_bus=event_bus1,
            config=config,
            session_id="session-1",
        )
        session1.state = DiscussionState.COMPLETED

        session2 = DiscussionSession(
            topic="Session Two",
            event_bus=event_bus2,
            config=config,
            session_id="session-2",
        )
        session2.state = DiscussionState.COMPLETED

        agent1 = MagicMock()
        agent1.name = "Agent One"
        agent1.type = "PERSONA"
        session1.agents["agent_1"] = agent1

        agent2 = MagicMock()
        agent2.name = "Agent Two"
        agent2.type = "PERSONA"
        session2.agents["agent_2"] = agent2

        msg1 = Message(
            id="msg_1",
            agent_id="agent_1",
            content="Message from session one.",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        session1.conversation_log.append(msg1)

        msg2 = Message(
            id="msg_2",
            agent_id="agent_2",
            content="Message from session two.",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        session2.conversation_log.append(msg2)

        store = get_session_store()
        store[session1.id] = session1
        store[session2.id] = session2

        response1 = await client.get(
            f"/api/discussion/{session1.id}/export?format=TEXT"
        )
        response2 = await client.get(
            f"/api/discussion/{session2.id}/export?format=TEXT"
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        content1 = response1.text
        content2 = response2.text

        assert "Session One" in content1
        assert "Message from session one." in content1
        assert "Session Two" not in content1
        assert "Message from session two." not in content1

        assert "Session Two" in content2
        assert "Message from session two." in content2
        assert "Session One" not in content2
        assert "Message from session one." not in content2
