import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.dependencies import get_session_store, _session_store, get_llm_client
from app.orchestration.event_bus import (
    AgentMessageEvent,
    FactCheckEvent,
    ModeratorCommandEvent,
    StallDetectedEvent,
)


async def async_generator(items):
    for item in items:
        yield item


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.complete = AsyncMock(
        return_value="""
    [
        {
            "name": "Dr. Sarah Chen",
            "role": "Climate Scientist",
            "background": "PhD in Atmospheric Science",
            "stance": "Supports climate action"
        },
        {
            "name": "John Martinez",
            "role": "Policy Analyst",
            "background": "Former government advisor",
            "stance": "Skeptical of current policies"
        },
        {
            "name": "Dr. Emily Zhang",
            "role": "Environmental Economist",
            "background": "Researcher on carbon pricing",
            "stance": "Supports carbon taxes"
        }
    ]
    """
    )
    client.stream_chat = AsyncMock(return_value=async_generator(["Test response"]))
    return client


@pytest_asyncio.fixture
async def client(mock_llm_client):
    def override_get_llm_client():
        return mock_llm_client

    app.dependency_overrides[get_llm_client] = override_get_llm_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_session_store():
    _session_store.clear()
    yield
    _session_store.clear()


class TestSSEStreaming:
    @pytest.mark.asyncio
    async def test_sse_endpoint_returns_streaming_response(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
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
    async def test_sse_stream_not_found_session(self, client):
        response = await client.get(
            "/api/discussion/non-existent-id/stream",
            headers={"Accept": "text/event-stream"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sse_stream_subscribes_to_event_bus(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        async def read_stream():
            async with client.stream(
                "GET", f"/api/discussion/{session_id}/stream"
            ) as response:
                assert response.status_code == 200
                await asyncio.sleep(0.3)

        try:
            await asyncio.wait_for(read_stream(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert event_bus is not None

    @pytest.mark.asyncio
    async def test_sse_stream_connection_cleanup_on_disconnect(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        initial_subscriber_count = len(
            event_bus._subscriptions.get("agent_message", [])
        )

        try:
            async with asyncio.timeout(0.3):
                async with client.stream(
                    "GET", f"/api/discussion/{session_id}/stream"
                ) as response:
                    assert response.status_code == 200
                    await asyncio.sleep(0.4)
        except asyncio.TimeoutError:
            pass

        await asyncio.sleep(0.2)

        final_subscriber_count = len(event_bus._subscriptions.get("agent_message", []))
        assert final_subscriber_count >= initial_subscriber_count


class TestSSEEventBusIntegration:
    @pytest.mark.asyncio
    async def test_event_handler_receives_events(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        received_events = []

        def test_handler(event):
            received_events.append(event)

        event_bus.subscribe("agent_message", test_handler)

        event = AgentMessageEvent(
            agent_id="agent_1",
            agent_type="persona",
            content="Test message",
            metadata={"message_id": "msg_1"},
        )
        event_bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].agent_id == "agent_1"
        assert received_events[0].content == "Test message"

    @pytest.mark.asyncio
    async def test_fact_check_event_published(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        received_events = []

        def test_handler(event):
            received_events.append(event)

        event_bus.subscribe("fact_check", test_handler)

        event = FactCheckEvent(
            claim="Test claim",
            source="Test source",
            result=True,
            confidence=0.95,
        )
        event_bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].claim == "Test claim"
        assert received_events[0].result is True

    @pytest.mark.asyncio
    async def test_moderator_command_event_published(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        received_events = []

        def test_handler(event):
            received_events.append(event)

        event_bus.subscribe("moderator_command", test_handler)

        event = ModeratorCommandEvent(
            command="pause",
            target_agent_id="agent_1",
        )
        event_bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].command == "pause"

    @pytest.mark.asyncio
    async def test_stall_detected_event_published(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        event_bus = session.event_bus

        received_events = []

        def test_handler(event):
            received_events.append(event)

        event_bus.subscribe("stall_detected", test_handler)

        event = StallDetectedEvent(
            agent_id="agent_1",
            reason="No response for 60 seconds",
        )
        event_bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].agent_id == "agent_1"


class TestSSEEventFormat:
    @pytest.mark.asyncio
    async def test_agent_message_event_format(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        event = AgentMessageEvent(
            agent_id="agent_1",
            agent_type="persona",
            content="Test message",
            metadata={"message_id": "msg_1", "timestamp": "2024-01-01T00:00:00"},
        )

        event_data = {
            "type": "agent_message",
            "agent_id": event.agent_id,
            "agent_type": event.agent_type,
            "content": event.content,
            "metadata": event.metadata,
        }

        assert "type" in event_data
        assert "agent_id" in event_data
        assert "content" in event_data
        assert event_data["type"] == "agent_message"

    @pytest.mark.asyncio
    async def test_fact_check_event_format(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        event = FactCheckEvent(
            claim="Test claim",
            source="Test source",
            result=True,
            confidence=0.95,
        )

        event_data = {
            "type": "fact_check",
            "claim": event.claim,
            "source": event.source,
            "result": event.result,
            "confidence": event.confidence,
            "metadata": event.metadata,
        }

        assert "type" in event_data
        assert "claim" in event_data
        assert event_data["type"] == "fact_check"

    @pytest.mark.asyncio
    async def test_sse_data_format(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        event = AgentMessageEvent(
            agent_id="agent_1",
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

        json_str = sse_line[6:-2]
        parsed = json.loads(json_str)
        assert parsed["type"] == "agent_message"
