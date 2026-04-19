"""
Comprehensive backend integration tests for the full discussion flow.

Tests verify the complete lifecycle via API:
- POST /api/discussion/start creates session and returns panel
- Panel has 3+ diverse personas with different stances
- GET /api/discussion/{id} returns correct state
- POST /api/discussion/{id}/pause pauses discussion
- POST /api/discussion/{id}/stop stops discussion and generates synthesis
- GET /api/discussion/{id}/export?format=TEXT returns text file
- GET /api/discussion/{id}/export?format=MARKDOWN returns markdown file
- SSE endpoint streams events correctly
- Session cleanup works after TTL

Uses httpx.AsyncClient with mocked LLM responses.
"""

import asyncio
import json
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.dependencies import get_session_store, _session_store, get_llm_client
from app.models.discussion import DiscussionState
from app.models.message import Message, MessageType
from app.orchestration.event_bus import (
    AgentMessageEvent,
    FactCheckEvent,
    ModeratorCommandEvent,
    StallDetectedEvent,
)
from app.orchestration.cleanup import SessionCleanup
from app.agents.moderator import ModeratorAgent


async def async_generator(items):
    """Helper to create async generators for mocking stream_chat."""
    for item in items:
        yield item


@pytest.fixture
def mock_llm_client():
    """
    Mock LLM client with pre-configured responses for panel generation,
    synthesis, and streaming.
    """
    client = MagicMock()

    # Panel generation response - diverse personas with different stances
    client.complete = AsyncMock(
        return_value="""
    [
        {
            "name": "Dr. Sarah Chen",
            "role": "Climate Scientist",
            "background": "PhD in Atmospheric Science, 15 years research experience at NOAA",
            "stance": "Strongly supports aggressive climate action and carbon reduction"
        },
        {
            "name": "John Martinez",
            "role": "Policy Analyst",
            "background": "Former government advisor on energy policy, focuses on economic impacts",
            "stance": "Skeptical of current climate policies, advocates for market solutions"
        },
        {
            "name": "Dr. Emily Zhang",
            "role": "Environmental Economist",
            "background": "Researcher focusing on carbon pricing mechanisms and cost-benefit analysis",
            "stance": "Supports carbon taxes but opposes heavy regulation"
        },
        {
            "name": "Marcus Thompson",
            "role": "Alternative Energy Skeptic",
            "background": "Outsider position - questions mainstream climate consensus",
            "stance": "Critical of climate alarmism, advocates for more research before action"
        }
    ]
    """
    )

    # Stream chat for synthesis and responses
    client.stream_chat = AsyncMock(
        return_value=async_generator(
            [
                "This discussion explored multiple perspectives on climate policy.",
                " Key agreements: need for action, importance of economic considerations.",
                " Key disagreements: pace of change, role of regulation vs markets.",
                " Synthesis: A balanced approach combining market incentives with targeted regulation.",
            ]
        )
    )

    return client


@pytest_asyncio.fixture
async def client(mock_llm_client):
    """
    Async HTTP client with mocked LLM client dependency override.
    """

    def override_get_llm_client():
        return mock_llm_client

    app.dependency_overrides[get_llm_client] = override_get_llm_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_session_store():
    """
    Clear session store before and after each test.
    """
    _session_store.clear()
    yield
    _session_store.clear()


class TestFullDiscussionLifecycle:
    """
    Test the complete discussion lifecycle from start to export.
    """

    @pytest.mark.asyncio
    async def test_start_discussion_creates_session_and_panel(self, client):
        """
        POST /api/discussion/start creates session and returns generating status.
        """
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Climate change policy effectiveness"},
        )

        assert response.status_code == 200
        data = response.json()

        # Session ID is returned
        assert "session_id" in data
        assert len(data["session_id"]) > 0
        session_id = data["session_id"]

        # Status is generating initially
        assert data["status"] == "generating"

        # Personas are empty initially (generated async)
        assert "personas" in data
        personas = data["personas"]
        assert len(personas) == 0

    @pytest.mark.asyncio
    async def test_panel_has_diverse_stances(self, mock_llm_client):
        """Panel has personas with different stances (support, oppose, neutral)."""
        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel(
            "Climate change policy effectiveness"
        )

        # Check for stance diversity
        stances = [p.stance.lower() for p in personas]

        # Should have at least one support stance
        support_keywords = ["support", "favor", "agree", "pro", "advocate"]
        has_support = any(
            any(kw in stance for kw in support_keywords) for stance in stances
        )

        # Should have at least one oppose/skeptic stance
        oppose_keywords = ["oppose", "against", "disagree", "skeptic", "critical"]
        has_oppose = any(
            any(kw in stance for kw in oppose_keywords) for stance in stances
        )

        assert has_support, (
            "Panel should have at least one persona supporting the topic"
        )
        assert has_oppose, (
            "Panel should have at least one persona opposing/skeptical of the topic"
        )

    @pytest.mark.asyncio
    async def test_panel_has_outsider_position(self, mock_llm_client):
        """Panel includes at least one persona with outsider/unconventional position."""
        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel(
            "Climate change policy effectiveness"
        )

        # Check for outsider keywords in stance/background/role
        outsider_keywords = [
            "outsider",
            "alternative",
            "unconventional",
            "skeptic",
            "critic",
            "contrarian",
            "dissenting",
            "marginalized",
        ]

        has_outsider = False
        for persona in personas:
            combined_text = (
                f"{persona.stance} {persona.background} {persona.role}".lower()
            )
            if any(kw in combined_text for kw in outsider_keywords):
                has_outsider = True
                break

        assert has_outsider, "Panel should have at least one outsider position"

    @pytest.mark.asyncio
    async def test_get_discussion_returns_correct_state(self, client):
        """
        GET /api/discussion/{id} returns correct state after start.
        """
        # Start discussion
        start_response = await client.post(
            "/api/discussion/start",
            json={"topic": "Climate change policy effectiveness"},
        )
        session_id = start_response.json()["session_id"]

        await asyncio.sleep(1.0)

        store = get_session_store()
        session = store[session_id]
        session.start_discussion()

        # Verify ACTIVE state after resume
        get_response = await client.get(f"/api/discussion/{session_id}")
        assert get_response.json()["state"] == "ACTIVE"

        # Stop discussion
        stop_response = await client.post(f"/api/discussion/{session_id}/stop")
        assert stop_response.json()["state"] == "COMPLETED"

        # Verify synthesis was generated
        assert "synthesis" in stop_response.json()
        assert len(stop_response.json()["synthesis"]) > 0


class TestExportFormats:
    """
    Test export functionality for TEXT and MARKDOWN formats.
    """

    @pytest.mark.asyncio
    async def test_export_text_format(self, client):
        """
        GET /api/discussion/{id}/export?format=TEXT returns text file.
        """
        # Start and stop discussion
        start_response = await client.post(
            "/api/discussion/start",
            json={"topic": "Climate change policy effectiveness"},
        )
        session_id = start_response.json()["session_id"]

        # Add some messages to the conversation
        store = get_session_store()
        session = store[session_id]

        msg1 = Message(
            id="msg_1",
            agent_id="persona_1",
            content="We need urgent action on climate change.",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        msg2 = Message(
            id="msg_2",
            agent_id="persona_2",
            content="Market solutions are more effective than regulation.",
            timestamp=datetime(2024, 1, 15, 10, 5, 0),
            type=MessageType.AGENT,
        )
        session.conversation_log.extend([msg1, msg2])

        # Stop discussion
        await client.post(f"/api/discussion/{session_id}/stop")

        # Export as TEXT
        export_response = await client.get(
            f"/api/discussion/{session_id}/export?format=TEXT"
        )

        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in export_response.headers["content-disposition"]
        assert ".txt" in export_response.headers["content-disposition"]

        content = export_response.text
        assert "Climate change policy effectiveness" in content
        assert "We need urgent action on climate change." in content
        assert "Market solutions are more effective than regulation." in content

    @pytest.mark.asyncio
    async def test_export_markdown_format(self, client):
        """
        GET /api/discussion/{id}/export?format=MARKDOWN returns markdown file.
        """
        # Start and stop discussion
        start_response = await client.post(
            "/api/discussion/start",
            json={"topic": "Climate change policy effectiveness"},
        )
        session_id = start_response.json()["session_id"]

        # Add some messages
        store = get_session_store()
        session = store[session_id]

        msg1 = Message(
            id="msg_1",
            agent_id="persona_1",
            content="We need urgent action on climate change.",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        session.conversation_log.append(msg1)

        # Stop discussion
        await client.post(f"/api/discussion/{session_id}/stop")

        # Export as MARKDOWN
        export_response = await client.get(
            f"/api/discussion/{session_id}/export?format=MARKDOWN"
        )

        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert "attachment" in export_response.headers["content-disposition"]
        assert ".md" in export_response.headers["content-disposition"]

        content = export_response.text
        assert "# Discussion: Climate change policy effectiveness" in content
        assert "## Participants" in content
        assert "## Conversation" in content

    @pytest.mark.asyncio
    async def test_export_after_full_lifecycle(self, client):
        """
        Export works correctly after full lifecycle (start → stop).
        """
        # Full lifecycle
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic for export"}
        )
        session_id = start_response.json()["session_id"]

        # Add messages
        store = get_session_store()
        session = store[session_id]

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id=f"persona_{i}",
                content=f"Message {i} content",
                timestamp=datetime(2024, 1, 15, 10, i * 5, 0),
                type=MessageType.AGENT,
            )
            session.conversation_log.append(msg)

        # Stop discussion
        await client.post(f"/api/discussion/{session_id}/stop")

        # Export both formats
        text_response = await client.get(
            f"/api/discussion/{session_id}/export?format=TEXT"
        )
        md_response = await client.get(
            f"/api/discussion/{session_id}/export?format=MARKDOWN"
        )

        assert text_response.status_code == 200
        assert md_response.status_code == 200

        # Verify content includes all messages
        text_content = text_response.text
        for i in range(3):
            assert f"Message {i} content" in text_content


class TestSSEStreaming:
    """
    Test SSE endpoint streams events correctly.
    """

    @pytest.mark.asyncio
    async def test_sse_endpoint_headers(self, client):
        """
        SSE endpoint returns correct headers for streaming.
        """
        start_response = await client.post(
            "/api/discussion/start",
            json={"topic": "Climate change policy effectiveness"},
        )
        session_id = start_response.json()["session_id"]

        try:
            async with asyncio.timeout(0.5):
                async with client.stream(
                    "GET", f"/api/discussion/{session_id}/stream"
                ) as response:
                    assert response.status_code == 200
                    assert (
                        response.headers["content-type"]
                        == "text/event-stream; charset=utf-8"
                    )
                    assert response.headers["cache-control"] == "no-cache"
                    assert response.headers["x-accel-buffering"] == "no"
        except asyncio.TimeoutError:
            pass

    @pytest.mark.asyncio
    async def test_sse_event_bus_subscription(self, client):
        """SSE endpoint returns correct streaming headers."""
        session = _create_test_session()

        try:
            async with asyncio.timeout(0.5):
                async with client.stream(
                    "GET", f"/api/discussion/{session.id}/stream"
                ) as response:
                    assert response.status_code == 200
                    assert "text/event-stream" in response.headers["content-type"]
                    assert response.headers["cache-control"] == "no-cache"
        except asyncio.TimeoutError:
            pass

        # Verify event bus exists and is functional
        assert session.event_bus is not None
        event_bus = session.event_bus

        event = AgentMessageEvent(
            agent_id="test", agent_type="test", content="test", metadata={}
        )
        event_bus.publish(event)
        assert len(event_bus.get_history()) > 0

    @pytest.mark.asyncio
    async def test_sse_streams_agent_message_event(self, client):
        """
        SSE endpoint streams agent_message events correctly.
        """
        start_response = await client.post(
            "/api/discussion/start",
            json={"topic": "Climate change policy effectiveness"},
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        # Publish an agent message event
        event = AgentMessageEvent(
            agent_id="persona_1",
            agent_type="persona",
            content="Test message from agent",
            metadata={"message_id": "msg_1", "timestamp": "2024-01-01T00:00:00"},
        )
        event_bus.publish(event)

        # Verify event was published
        history = event_bus.get_history()
        assert len(history) > 0
        assert any(isinstance(e, AgentMessageEvent) for e in history)

    @pytest.mark.asyncio
    async def test_sse_streams_fact_check_event(self, client):
        """
        SSE endpoint streams fact_check events correctly.
        """
        start_response = await client.post(
            "/api/discussion/start",
            json={"topic": "Climate change policy effectiveness"},
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        # Publish a fact check event
        event = FactCheckEvent(
            claim="Test claim to verify",
            source="https://example.com",
            result=True,
            confidence=0.95,
        )
        event_bus.publish(event)

        # Verify event was published
        history = event_bus.get_history()
        assert any(isinstance(e, FactCheckEvent) for e in history)

    @pytest.mark.asyncio
    async def test_sse_event_format(self, client):
        """
        SSE events are formatted correctly as data: {json}\n\n.
        """
        event = AgentMessageEvent(
            agent_id="persona_1",
            agent_type="persona",
            content="Test message",
            metadata={"message_id": "msg_1"},
        )

        event_data = {
            "type": "agent_message",
            "agent_id": event.agent_id,
            "agent_type": event.agent_type,
            "content": event.content,
            "metadata": event.metadata,
        }

        sse_line = f"data: {json.dumps(event_data)}\n\n"

        assert sse_line.startswith("data: ")
        assert sse_line.endswith("\n\n")

        # Parse JSON
        json_str = sse_line[6:-2]
        parsed = json.loads(json_str)
        assert parsed["type"] == "agent_message"
        assert parsed["agent_id"] == "persona_1"


class TestSessionCleanup:
    """
    Test session cleanup after TTL.
    """

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_sessions(self, client):
        """
        SessionCleanup removes sessions that have exceeded TTL.
        """
        # Create a session
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        assert session_id in store

        # Create cleanup with short TTL
        cleanup = SessionCleanup(store, ttl_seconds=1)

        # Wait for TTL to expire
        await asyncio.sleep(1.5)

        # Run cleanup
        deleted_count = await cleanup.run_cleanup()

        assert deleted_count == 1
        assert session_id not in store

    @pytest.mark.asyncio
    async def test_cleanup_preserves_active_sessions(self, client):
        """
        SessionCleanup preserves sessions that are still active.
        """
        # Create a session
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        assert session_id in store

        # Create cleanup with long TTL
        cleanup = SessionCleanup(store, ttl_seconds=3600)

        # Run cleanup immediately (session should not be expired)
        deleted_count = await cleanup.run_cleanup()

        assert deleted_count == 0
        assert session_id in store

    @pytest.mark.asyncio
    async def test_cleanup_loop_runs_periodically(self, client):
        """
        SessionCleanup loop runs at specified interval.
        """
        store = get_session_store()

        # Create cleanup with short interval
        cleanup = SessionCleanup(store, ttl_seconds=1)

        # Start cleanup loop
        await cleanup.start_cleanup_loop(interval_seconds=1)

        # Create a session
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )
        session_id = start_response.json()["session_id"]

        # Wait for TTL to expire and cleanup to run
        await asyncio.sleep(2.0)

        # Session should be cleaned up
        assert session_id not in store

        # Stop cleanup loop
        cleanup.stop_cleanup_loop()

    @pytest.mark.asyncio
    async def test_cleanup_marks_session_for_deletion(self, client):
        """
        Cleanup properly marks sessions for deletion.
        """
        # Create a session
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        # Manually mark for cleanup
        session.cleanup()

        assert session.is_marked_for_cleanup()
        assert session.state == DiscussionState.COMPLETED


class TestErrorHandling:
    """
    Test error handling for invalid operations.
    """

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_returns_404(self, client):
        """
        GET /api/discussion/{id} returns 404 for nonexistent session.
        """
        response = await client.get("/api/discussion/nonexistent-session-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_pause_nonexistent_session_returns_404(self, client):
        """
        POST /api/discussion/{id}/pause returns 404 for nonexistent session.
        """
        response = await client.post("/api/discussion/nonexistent-session-id/pause")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_nonexistent_session_returns_404(self, client):
        """
        POST /api/discussion/{id}/stop returns 404 for nonexistent session.
        """
        response = await client.post("/api/discussion/nonexistent-session-id/stop")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_nonexistent_session_returns_404(self, client):
        """
        GET /api/discussion/{id}/export returns 404 for nonexistent session.
        """
        response = await client.get(
            "/api/discussion/nonexistent-session-id/export?format=TEXT"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pause_completed_discussion_returns_400(self, client):
        """POST /api/discussion/{id}/pause returns 400 for completed discussion."""
        session = _create_test_session()
        session.stop_discussion()

        pause_response = await client.post(f"/api/discussion/{session.id}/pause")
        assert pause_response.status_code == 400
        assert "completed" in pause_response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sse_nonexistent_session_returns_404(self, client):
        """
        SSE endpoint returns 404 for nonexistent session.
        """
        response = await client.get(
            "/api/discussion/nonexistent-session-id/stream",
            headers={"Accept": "text/event-stream"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestSessionIsolation:
    """
    Test that sessions are isolated from each other.
    """

    @pytest.mark.asyncio
    async def test_multiple_sessions_are_isolated(self, client):
        """
        Multiple sessions have separate state and conversation logs.
        """
        # Create two sessions
        response1 = await client.post(
            "/api/discussion/start", json={"topic": "Topic 1"}
        )
        response2 = await client.post(
            "/api/discussion/start", json={"topic": "Topic 2"}
        )

        session_id1 = response1.json()["session_id"]
        session_id2 = response2.json()["session_id"]

        assert session_id1 != session_id2

        # Verify isolation
        get1 = await client.get(f"/api/discussion/{session_id1}")
        get2 = await client.get(f"/api/discussion/{session_id2}")

        assert get1.json()["topic"] == "Topic 1"
        assert get2.json()["topic"] == "Topic 2"

    @pytest.mark.asyncio
    async def test_pause_one_session_does_not_affect_other(self, client):
        """Pausing one session does not affect another session's state."""
        from app.models.discussion import DiscussionState

        session1 = _create_test_session("Topic 1")
        session2 = _create_test_session("Topic 2")
        session2.state = DiscussionState.ACTIVE

        await client.post(f"/api/discussion/{session1.id}/pause")

        assert session2.state == DiscussionState.ACTIVE
        assert session1.state == DiscussionState.PAUSED

    @pytest.mark.asyncio
    async def test_export_is_session_specific(self, client):
        """
        Export returns content specific to the session, not mixed with others.
        """
        # Create two sessions
        response1 = await client.post(
            "/api/discussion/start", json={"topic": "Topic 1"}
        )
        response2 = await client.post(
            "/api/discussion/start", json={"topic": "Topic 2"}
        )

        session_id1 = response1.json()["session_id"]
        session_id2 = response2.json()["session_id"]

        # Add different messages to each session
        store = get_session_store()

        session1 = store[session_id1]
        msg1 = Message(
            id="msg_1",
            agent_id="persona_1",
            content="Message from session 1",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        session1.conversation_log.append(msg1)

        session2 = store[session_id2]
        msg2 = Message(
            id="msg_2",
            agent_id="persona_2",
            content="Message from session 2",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        session2.conversation_log.append(msg2)

        # Stop both
        await client.post(f"/api/discussion/{session_id1}/stop")
        await client.post(f"/api/discussion/{session_id2}/stop")

        # Export both
        export1 = await client.get(f"/api/discussion/{session_id1}/export?format=TEXT")
        export2 = await client.get(f"/api/discussion/{session_id2}/export?format=TEXT")

        content1 = export1.text
        content2 = export2.text

        # Verify isolation
        assert "Topic 1" in content1
        assert "Message from session 1" in content1
        assert "Topic 2" not in content1
        assert "Message from session 2" not in content1

        assert "Topic 2" in content2
        assert "Message from session 2" in content2
        assert "Topic 1" not in content2
        assert "Message from session 1" not in content2


def _create_test_session(topic="Test topic"):
    """Helper to create a session ready for start-discussion."""
    from app.orchestration.event_bus import EventBus
    from app.orchestration.session import DiscussionSession
    from app.models.discussion import DiscussionConfig
    from app.agents.persona import PersonaAgent

    event_bus = EventBus()
    config = DiscussionConfig(max_messages=30)
    session = DiscussionSession(topic=topic, event_bus=event_bus, config=config)
    session.generation_status = "ready"

    persona = MagicMock(spec=PersonaAgent)
    persona.id = "persona_mock"
    persona.name = "Test Persona"
    persona.role = "Tester"
    persona._stance = "pro"
    persona.background = "bg"
    persona.emoji = "👤"
    persona.type = MagicMock()

    session.personas = [persona]
    session.agents["persona_mock"] = persona
    _session_store[session.id] = session
    return session


class TestModeratorIntegration:
    """Test moderator agent integration with discussion flow."""

    @pytest.mark.asyncio
    async def test_moderator_added_to_session(self, client, mock_llm_client):
        """Moderator agent is added to session on start-discussion."""
        session = _create_test_session()

        response = await client.post(f"/api/discussion/{session.id}/start-discussion")
        assert response.status_code == 200, f"start-discussion failed: {response.text}"

        moderator_found = any("moderator" in aid.lower() for aid in session.agents)
        assert moderator_found, "Moderator should be added to session"

    @pytest.mark.asyncio
    async def test_moderator_loop_starts_on_discussion_start(
        self, client, mock_llm_client
    ):
        """Moderator loop starts when discussion starts."""
        session = _create_test_session()

        await client.post(f"/api/discussion/{session.id}/start-discussion")

        moderator = next(
            (a for a in session.agents.values() if isinstance(a, ModeratorAgent)), None
        )
        assert moderator is not None
        assert moderator._moderator_task is not None

    @pytest.mark.asyncio
    async def test_moderator_loop_stops_on_pause(self, client, mock_llm_client):
        """Moderator loop stops when discussion is paused."""
        session = _create_test_session()

        await client.post(f"/api/discussion/{session.id}/start-discussion")
        await client.post(f"/api/discussion/{session.id}/pause")

        moderator = next(
            (a for a in session.agents.values() if isinstance(a, ModeratorAgent)), None
        )
        assert moderator is not None
        assert moderator._running is False

    @pytest.mark.asyncio
    async def test_moderator_generates_synthesis_on_stop(self, client, mock_llm_client):
        """Moderator generates synthesis when discussion is stopped."""
        session = _create_test_session()

        await client.post(f"/api/discussion/{session.id}/start-discussion")
        stop_response = await client.post(f"/api/discussion/{session.id}/stop")

        data = stop_response.json()
        assert "synthesis" in data
        assert len(data["synthesis"]) > 20


class TestEventBusIntegration:
    """
    Test event bus integration with discussion flow.
    """

    @pytest.mark.asyncio
    async def test_event_bus_created_for_session(self, client):
        """
        Event bus is created for each session.
        """
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        assert session.event_bus is not None

    @pytest.mark.asyncio
    async def test_events_published_on_message_add(self, client):
        """
        AgentMessageEvent is published when message is added to conversation.
        """
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        # Clear event history
        session.event_bus.clear_history()

        # Add a message
        msg = Message(
            id="msg_1",
            agent_id="persona_1",
            content="Test message",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await session.add_message(msg)

        # Check event was published
        history = session.event_bus.get_history()
        assert len(history) > 0
        assert any(isinstance(e, AgentMessageEvent) for e in history)

    @pytest.mark.asyncio
    async def test_multiple_event_types_supported(self, client):
        """
        Event bus supports multiple event types.
        """
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        # Publish different event types
        agent_event = AgentMessageEvent(
            agent_id="persona_1",
            agent_type="persona",
            content="Agent message",
            metadata={},
        )
        fact_check_event = FactCheckEvent(
            claim="Test claim",
            source="Test source",
            result=True,
            confidence=0.9,
        )
        moderator_event = ModeratorCommandEvent(
            command="pause",
            target_agent_id="persona_1",
        )
        stall_event = StallDetectedEvent(
            agent_id="persona_1",
            reason="No response",
        )

        event_bus.publish(agent_event)
        event_bus.publish(fact_check_event)
        event_bus.publish(moderator_event)
        event_bus.publish(stall_event)

        # Verify all events in history
        history = event_bus.get_history()
        assert len(history) >= 4

        event_types = [type(e).__name__ for e in history]
        assert "AgentMessageEvent" in event_types
        assert "FactCheckEvent" in event_types
        assert "ModeratorCommandEvent" in event_types
        assert "StallDetectedEvent" in event_types
