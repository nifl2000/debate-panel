import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.dependencies import get_session_store, _session_store, get_llm_client
from app.models.discussion import DiscussionState


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
            "background": "PhD in Atmospheric Science, 15 years research experience",
            "stance": "Strongly supports aggressive climate action"
        },
        {
            "name": "John Martinez",
            "role": "Policy Analyst",
            "background": "Former government advisor on energy policy",
            "stance": "Skeptical of current climate policies, advocates for market solutions"
        },
        {
            "name": "Dr. Emily Zhang",
            "role": "Environmental Economist",
            "background": "Researcher focusing on carbon pricing mechanisms",
            "stance": "Supports carbon taxes but opposes heavy regulation"
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


class TestStartDiscussion:
    @pytest.mark.asyncio
    async def test_start_discussion_success(self, client):
        response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0
        assert "personas" in data
        assert data["status"] == "generating"
        assert len(data["personas"]) == 0

    @pytest.mark.asyncio
    async def test_start_discussion_missing_topic(self, client):
        response = await client.post("/api/discussion/start", json={})

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_discussion_empty_topic(self, client):
        response = await client.post("/api/discussion/start", json={"topic": ""})

        assert response.status_code == 200


class TestGetDiscussion:
    @pytest.mark.asyncio
    async def test_get_discussion_success(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        response = await client.get(f"/api/discussion/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["topic"] == "Climate change policy"
        assert data["state"] == "PAUSED"
        assert "messages" in data
        assert isinstance(data["messages"], list)
        assert "agents" in data

    @pytest.mark.asyncio
    async def test_get_discussion_not_found(self, client):
        response = await client.get("/api/discussion/non-existent-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestPauseDiscussion:
    @pytest.mark.asyncio
    async def test_pause_discussion_success(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        response = await client.post(f"/api/discussion/{session_id}/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["state"] == "PAUSED"
        assert "paused" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_pause_discussion_not_found(self, client):
        response = await client.post("/api/discussion/non-existent-id/pause")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pause_completed_discussion(self, client):
        from app.api.dependencies import _session_store
        from app.orchestration.event_bus import EventBus
        from app.orchestration.session import DiscussionSession
        from app.models.discussion import DiscussionConfig

        event_bus = EventBus()
        config = DiscussionConfig(max_messages=30)
        session = DiscussionSession(topic="Test", event_bus=event_bus, config=config)
        session.generation_status = "ready"
        session.personas = []
        _session_store[session.id] = session

        await client.post(f"/api/discussion/{session.id}/stop")

        response = await client.post(f"/api/discussion/{session.id}/pause")

        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()


class TestStopDiscussion:
    @pytest.mark.asyncio
    async def test_stop_discussion_success(self, client, mock_llm_client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        mock_llm_client.stream_chat = AsyncMock(
            return_value=async_generator(["This is a synthesis of the discussion."])
        )

        response = await client.post(f"/api/discussion/{session_id}/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["state"] == "COMPLETED"
        assert "synthesis" in data

    @pytest.mark.asyncio
    async def test_stop_discussion_not_found(self, client):
        response = await client.post("/api/discussion/non-existent-id/stop")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_stop_without_moderator(self, client):
        start_response = await client.post(
            "/api/discussion/start", json={"topic": "Climate change policy"}
        )
        session_id = start_response.json()["session_id"]

        import asyncio

        for _ in range(10):
            await asyncio.sleep(0.5)
            status_response = await client.get(f"/api/discussion/{session_id}/status")
            if status_response.json()["status"] == "ready":
                break

        store = get_session_store()
        session = store[session_id]
        agents_to_remove = [
            aid for aid, a in session.agents.items() if "moderator" in aid
        ]
        for aid in agents_to_remove:
            del session.agents[aid]

        response = await client.post(f"/api/discussion/{session_id}/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "COMPLETED"
        assert data["synthesis"] == "Discussion stopped."


class TestSessionStore:
    @pytest.mark.asyncio
    async def test_session_store_isolation(self, client):
        response1 = await client.post(
            "/api/discussion/start", json={"topic": "Topic 1"}
        )
        response2 = await client.post(
            "/api/discussion/start", json={"topic": "Topic 2"}
        )

        session_id1 = response1.json()["session_id"]
        session_id2 = response2.json()["session_id"]

        assert session_id1 != session_id2

        get1 = await client.get(f"/api/discussion/{session_id1}")
        get2 = await client.get(f"/api/discussion/{session_id2}")

        assert get1.json()["topic"] == "Topic 1"
        assert get2.json()["topic"] == "Topic 2"


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_not_triggered(self, client):
        response = await client.post(
            "/api/discussion/start", json={"topic": "Test topic"}
        )

        assert response.status_code == 200
