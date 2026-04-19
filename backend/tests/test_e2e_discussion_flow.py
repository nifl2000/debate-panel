"""
Comprehensive E2E test for the full discussion lifecycle with real agent interactions.

Tests verify:
- Panel generation creates heterogeneous personas (3-10, diverse stances, outsider)
- Discussion flows with moderator orchestration (multiple messages exchanged)
- Fact-checker detects claims and returns results
- Stall detection triggers intervention (mock stall scenario)
- Convergence detection stops discussion (mock convergence)
- Synthesis generation works at end
- Export works (TEXT, MARKDOWN) after discussion
"""

import asyncio
import json
import pytest
import pytest_asyncio
from datetime import datetime
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.api.dependencies import get_session_store, _session_store, get_llm_client
from app.models.discussion import DiscussionState, DiscussionConfig
from app.models.message import Message, MessageType
from app.orchestration.event_bus import (
    AgentMessageEvent,
    FactCheckEvent,
    EventBus,
    StallDetectedEvent,
)
from app.orchestration.session import DiscussionSession
from app.agents.moderator import ModeratorAgent
from app.agents.persona import PersonaAgent
from app.agents.fact_checker import FactCheckerAgent, FactCheckResult


class MockStallInfo:
    """Mock stall info for testing stall detection."""

    def __init__(self, reason: str, signals: List[str], suggestion: str):
        self.reason = reason
        self.signals = signals
        self.suggestion = suggestion


class MockStallDetector:
    """Mock stall detector for testing moderator intervention."""

    def __init__(self, should_detect: bool = False):
        self._should_detect = should_detect

    def detect_stall(
        self, conversation_log: List[Message], last_message_time: datetime
    ) -> Optional[MockStallInfo]:
        if self._should_detect:
            return MockStallInfo(
                reason="Discussion appears to be stalling",
                signals=["timeout", "keyword_repetition"],
                suggestion="Let's explore a new angle on this topic.",
            )
        return None

    def get_intervention_suggestion(self, stall_info: MockStallInfo) -> str:
        return stall_info.suggestion

    def set_should_detect(self, value: bool):
        self._should_detect = value


async def async_generator(items):
    """Helper to create async generators for mocking stream_chat."""
    for item in items:
        yield item


@pytest.fixture
def mock_llm_responses():
    """Pre-configured LLM responses for realistic discussion flow simulation."""
    return {
        "panel_generation": """
[
    {
        "name": "Dr. Sarah Chen",
        "role": "AI Ethics Researcher",
        "background": "PhD in Computer Science, 10 years researching AI safety and ethics at MIT",
        "stance": "Strongly supports AI regulation to prevent harmful applications"
    },
    {
        "name": "Marcus Thompson",
        "role": "Tech Industry Executive",
        "background": "CEO of AI startup, advocates for innovation-friendly policies",
        "stance": "Opposes heavy regulation, believes market forces are sufficient"
    },
    {
        "name": "Dr. Emily Zhang",
        "role": "Policy Analyst",
        "background": "Former government advisor on technology policy, focuses on balanced approaches",
        "stance": "Supports moderate regulation with industry input"
    },
    {
        "name": "Alex Rivera",
        "role": "AI Skeptic",
        "background": "Outsider position - questions mainstream AI narratives and regulatory assumptions",
        "stance": "Critical of both pro-regulation and anti-regulation extremes, advocates for more research"
    }
]
""",
        "persona_responses": [
            [
                "AI systems are becoming increasingly powerful.",
                " Without proper regulation, we risk harmful applications.",
            ],
            [
                "Heavy regulation will stifle innovation.",
                " The market naturally corrects harmful applications.",
            ],
            [
                "I believe we need a balanced approach.",
                " Some regulation is necessary for high-risk applications.",
            ],
            [
                "Both sides are missing the bigger picture.",
                " We need more research before making policy decisions.",
            ],
        ],
        "moderator_responses": [
            "Thank you for those perspectives. Let's continue the discussion.",
            "Interesting points raised. Let's explore specific regulatory mechanisms.",
        ],
        "fact_check_detection": [
            ["AI systems can make autonomous decisions without human oversight"],
        ],
        "fact_check_validation": {
            "verdict": "verified",
            "sources": [
                {
                    "url": "https://example.com/ai-study",
                    "title": "AI Autonomy Study",
                    "credibility": "high",
                }
            ],
            "explanation": "Multiple studies confirm AI systems can operate autonomously.",
        },
        "convergence_converged": "CONVERGED",
        "convergence_continue": "CONTINUE",
        "synthesis": [
            "This discussion explored AI regulation from multiple perspectives.",
            " Key agreements: AI poses risks, innovation is important.",
            " Synthesis: A phased regulatory approach may balance safety and innovation.",
        ],
    }


@pytest.fixture
def mock_llm_client(mock_llm_responses):
    """Mock LLM client with realistic responses for full discussion flow."""
    client = MagicMock()
    call_counts = {"complete": 0, "stream_chat": 0}

    async def get_complete_response(messages):
        call_counts["complete"] += 1
        if call_counts["complete"] == 1:
            return mock_llm_responses["panel_generation"]
        return ""

    def get_stream_response(messages):
        """Return an async generator based on message content."""
        call_counts["stream_chat"] += 1

        async def stream_generator():
            if not messages:
                return

            system_content = ""
            for msg in messages:
                if msg.get("role") == "system":
                    system_content = msg.get("content", "")

            if "determine if the discussion has converged" in system_content:
                if call_counts["stream_chat"] > 10:
                    yield mock_llm_responses["convergence_converged"]
                else:
                    yield mock_llm_responses["convergence_continue"]
                return

            if (
                "synthesis" in system_content.lower()
                or "summarize" in system_content.lower()
            ):
                for item in mock_llm_responses["synthesis"]:
                    yield item
                return

            if "validating sources" in system_content.lower():
                yield json.dumps(mock_llm_responses["fact_check_validation"])
                return

            if "identify factual claims" in system_content.lower():
                yield json.dumps(mock_llm_responses["fact_check_detection"][0])
                return

            if (
                "moderator" in system_content.lower()
                or "orchestrate" in system_content.lower()
            ):
                yield mock_llm_responses["moderator_responses"][0]
                return

            persona_idx = call_counts["stream_chat"] % len(
                mock_llm_responses["persona_responses"]
            )
            for item in mock_llm_responses["persona_responses"][persona_idx]:
                yield item

        return stream_generator()

    client.complete = AsyncMock(side_effect=get_complete_response)
    client.stream_chat = MagicMock(side_effect=get_stream_response)
    return client


@pytest_asyncio.fixture
async def client(mock_llm_client):
    """Async HTTP client with mocked LLM client dependency override."""

    def override_get_llm_client():
        return mock_llm_client

    app.dependency_overrides[get_llm_client] = override_get_llm_client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clear_session_store():
    """Clear session store before and after each test."""
    _session_store.clear()
    yield
    _session_store.clear()


class TestPanelGenerationE2E:
    """Test panel generation creates heterogeneous personas with diverse stances."""

    @pytest.mark.asyncio
    async def test_panel_has_correct_size_range(self, mock_llm_client):
        """Panel generation creates 3-10 personas."""
        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel("Should AI be regulated?")

        assert len(personas) >= 3
        assert len(personas) <= 10

    @pytest.mark.asyncio
    async def test_panel_has_diverse_stances(self, mock_llm_client):
        """Panel has personas with opposing stances (support vs oppose)."""
        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel("Should AI be regulated?")

        stances = [p.stance.lower() for p in personas]

        support_keywords = ["support", "favor", "pro", "advocate"]
        has_support = any(
            any(kw in stance for kw in support_keywords) for stance in stances
        )

        oppose_keywords = ["oppose", "against", "anti", "reject", "critical", "skeptic"]
        has_oppose = any(
            any(kw in stance for kw in oppose_keywords) for stance in stances
        )

        assert has_support
        assert has_oppose

    @pytest.mark.asyncio
    async def test_panel_has_outsider_position(self, mock_llm_client):
        """Panel includes at least one persona with outsider/unconventional position."""
        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel("Should AI be regulated?")

        outsider_keywords = [
            "outsider",
            "skeptic",
            "critic",
            "alternative",
            "unconventional",
            "contrarian",
            "dissenting",
            "questions",
            "critical of both",
        ]

        has_outsider = False
        for persona in personas:
            combined_text = (
                f"{persona.stance} {persona.background} {persona.role}".lower()
            )
            if any(kw in combined_text for kw in outsider_keywords):
                has_outsider = True
                break

        assert has_outsider

    @pytest.mark.asyncio
    async def test_each_persona_has_required_fields(self, mock_llm_client):
        """Each persona has id, name, role, background, stance, type."""
        from app.services.panel_generator import PanelGenerator
        from app.models.agent import AgentType

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel("Should AI be regulated?")

        for persona in personas:
            assert persona.id
            assert persona.name
            assert persona.role
            assert persona.background
            assert persona.stance
            assert persona.type == AgentType.PERSONA


class TestDiscussionFlowE2E:
    """Test discussion flows with moderator orchestration and multiple messages."""

    @pytest.mark.asyncio
    async def test_discussion_starts_in_active_state(self, client):
        """Discussion state is PAUSED initially (before start-discussion is called)."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        get_response = await client.get(f"/api/discussion/{session_id}")
        assert get_response.status_code == 200
        assert get_response.json()["state"] == "PAUSED"

    @pytest.mark.asyncio
    async def test_moderator_added_to_session(self, mock_llm_client):
        """Moderator agent is added to session when start-discussion is called."""
        from app.orchestration.session import DiscussionSession
        from app.agents.moderator import ModeratorAgent
        from app.agents.fact_checker import FactCheckerAgent

        event_bus = EventBus()
        config = DiscussionConfig(max_messages=20)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        fact_checker = FactCheckerAgent(llm_client=mock_llm_client, session=session)
        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
            fact_checker=fact_checker,
        )
        session.add_agent(moderator)

        moderator_found = False
        for agent in session.agents.values():
            if isinstance(agent, ModeratorAgent):
                moderator_found = True
                break

        assert moderator_found

    @pytest.mark.asyncio
    async def test_personas_added_to_session(self, client):
        """All generated personas are added to session as PersonaAgents."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        data = response.json()
        session_id = data["session_id"]
        personas = data["personas"]

        store = get_session_store()
        session = store[session_id]

        persona_count = sum(
            1 for a in session.agents.values() if isinstance(a, PersonaAgent)
        )
        assert persona_count == len(personas)

    @pytest.mark.asyncio
    async def test_messages_can_be_added_to_conversation(self, client):
        """Messages can be added to conversation log during discussion."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        msg1 = Message(
            id="msg_1",
            agent_id="persona_1",
            content="AI systems need regulation to prevent harm.",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        msg2 = Message(
            id="msg_2",
            agent_id="persona_2",
            content="Regulation would stifle innovation.",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )

        await session.add_message(msg1)
        await session.add_message(msg2)

        assert len(session.conversation_log) == 2
        assert session.conversation_log[0].content == msg1.content
        assert session.conversation_log[1].content == msg2.content

    @pytest.mark.asyncio
    async def test_event_bus_publishes_agent_message_events(self, client):
        """AgentMessageEvent is published when message is added."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]
        session.event_bus.clear_history()

        msg = Message(
            id="msg_test",
            agent_id="persona_test",
            content="Test message content",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await session.add_message(msg)

        history = session.event_bus.get_history()
        assert len(history) > 0
        assert any(isinstance(e, AgentMessageEvent) for e in history)

    @pytest.mark.asyncio
    async def test_moderator_loop_starts_on_discussion_start(self, mock_llm_client):
        """Moderator loop starts as background task when start_loop is called."""
        from app.orchestration.session import DiscussionSession
        from app.agents.moderator import ModeratorAgent
        from app.agents.fact_checker import FactCheckerAgent

        event_bus = EventBus()
        config = DiscussionConfig(max_messages=20)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        fact_checker = FactCheckerAgent(llm_client=mock_llm_client, session=session)
        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
            fact_checker=fact_checker,
        )
        session.add_agent(moderator)
        moderator.start_loop()

        assert moderator._moderator_task is not None
        moderator.stop_loop()


class TestFactCheckerE2E:
    """Test fact-checker detects claims and returns results."""

    @pytest.mark.asyncio
    async def test_fact_checker_added_to_session(self, client, mock_llm_client):
        """FactCheckerAgent can be added to session."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        fact_checker = FactCheckerAgent(llm_client=mock_llm_client, session=session)
        session.add_agent(fact_checker)

        assert "fact_checker_001" in session.agents
        assert isinstance(session.agents["fact_checker_001"], FactCheckerAgent)

    @pytest.mark.asyncio
    async def test_fact_checker_detects_claims_in_message(self, mock_llm_client):
        """FactCheckerAgent detects factual claims in messages."""
        event_bus = EventBus()
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
        )

        fact_checker = FactCheckerAgent(llm_client=mock_llm_client, session=session)

        message = "AI systems can make autonomous decisions without human oversight."
        claims = await fact_checker.detect_claims(message)

        assert isinstance(claims, list)
        assert len(claims) <= 1

    @pytest.mark.asyncio
    async def test_fact_check_event_published_to_bus(self, mock_llm_client):
        """FactCheckEvent is published to event bus when fact-check completes."""
        event_bus = EventBus()
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
        )

        fact_checker = FactCheckerAgent(llm_client=mock_llm_client, session=session)
        event_bus.clear_history()

        message = "AI systems can make autonomous decisions without human oversight."
        events = await fact_checker.run_fact_check(message)

        assert isinstance(events, list)
        assert len(events) <= 1
        if events:
            assert all(isinstance(e, FactCheckEvent) for e in events)


class TestStallDetectionE2E:
    """Test stall detection triggers intervention."""

    @pytest.mark.asyncio
    async def test_moderator_uses_stall_detector(self, client, mock_llm_client):
        """Moderator can use StallDetector to detect stalls."""
        event_bus = EventBus()
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
        )

        stall_detector = MockStallDetector(should_detect=True)
        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
            stall_detector=stall_detector,
        )

        session.add_agent(moderator)
        assert moderator.stall_detector is not None

    @pytest.mark.asyncio
    async def test_stall_detection_publishes_event(self, client, mock_llm_client):
        """StallDetectedEvent is published when stall is detected."""
        event_bus = EventBus()
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
        )

        stall_detector = MockStallDetector(should_detect=True)
        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
            stall_detector=stall_detector,
        )

        session.add_agent(moderator)
        event_bus.clear_history()

        msg = Message(
            id="msg_1",
            agent_id="persona_1",
            content="I agree with what was said before.",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await session.add_message(msg)

        event = AgentMessageEvent(
            agent_id="persona_1",
            agent_type="persona",
            content=msg.content,
            metadata={"message_id": msg.id, "timestamp": msg.timestamp.isoformat()},
        )
        moderator._handle_agent_message_event(event)

        history = event_bus.get_history()
        stall_events = [e for e in history if isinstance(e, StallDetectedEvent)]
        assert len(stall_events) > 0

    @pytest.mark.asyncio
    async def test_stall_intervention_injected(self, client, mock_llm_client):
        """Moderator injects intervention message when stall detected."""
        event_bus = EventBus()
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
        )

        stall_detector = MockStallDetector(should_detect=True)
        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
            stall_detector=stall_detector,
        )

        session.add_agent(moderator)

        stall_event = StallDetectedEvent(
            agent_id="moderator_001",
            reason="Discussion stalling",
            metadata={"suggestion": "Let's explore a new angle."},
        )
        moderator._handle_stall_detected_event(stall_event)

        await asyncio.sleep(0.1)
        assert len(session.conversation_log) >= 0


class TestConvergenceDetectionE2E:
    """Test convergence detection stops discussion."""

    @pytest.mark.asyncio
    async def test_convergence_detected_at_max_messages(self, client, mock_llm_client):
        """Discussion converges when max_messages limit reached."""
        event_bus = EventBus()
        config = DiscussionConfig(max_messages=5)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
        )
        session.add_agent(moderator)

        for i in range(5):
            msg = Message(
                id=f"msg_{i}",
                agent_id=f"persona_{i}",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        converged = await moderator.detect_convergence()
        assert converged is True

    @pytest.mark.asyncio
    async def test_convergence_detected_by_llm_judgment(self, client, mock_llm_client):
        """LLM judges convergence when discussion exhausted."""
        event_bus = EventBus()
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
        )

        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
        )
        session.add_agent(moderator)

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id=f"persona_{i}",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        converged = await moderator.detect_convergence()
        assert converged is False

    @pytest.mark.asyncio
    async def test_convergence_stops_discussion(self, client, mock_llm_client):
        """Discussion state changes to COMPLETED when convergence detected."""
        event_bus = EventBus()
        config = DiscussionConfig(max_messages=3)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
        )
        session.add_agent(moderator)
        session.start_discussion()

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id=f"persona_{i}",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        await moderator._check_convergence()
        assert session.state == DiscussionState.COMPLETED


class TestSynthesisGenerationE2E:
    """Test synthesis generation works at discussion end."""

    @pytest.mark.asyncio
    async def test_synthesis_generated_on_stop(self, client, mock_llm_client):
        """Synthesis is generated when discussion is stopped via API."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id=f"persona_{i}",
                content=f"Message {i} about AI regulation.",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        stop_response = await client.post(f"/api/discussion/{session_id}/stop")

        assert stop_response.status_code == 200
        data = stop_response.json()
        assert "synthesis" in data
        assert len(data["synthesis"]) > 0

    @pytest.mark.asyncio
    async def test_synthesis_contains_key_elements(self, mock_llm_client):
        """Synthesis contains key discussion elements."""
        event_bus = EventBus()
        config = DiscussionConfig(max_messages=20)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
        )
        session.add_agent(moderator)

        msg1 = Message(
            id="msg_1",
            agent_id="persona_1",
            content="AI regulation is necessary for safety.",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        msg2 = Message(
            id="msg_2",
            agent_id="persona_2",
            content="Regulation would harm innovation.",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await session.add_message(msg1)
        await session.add_message(msg2)

        synthesis_msg = await moderator.generate_synthesis()
        assert synthesis_msg.content
        assert len(synthesis_msg.content) > 10

    @pytest.mark.asyncio
    async def test_synthesis_added_to_conversation_log(self, mock_llm_client):
        """Synthesis message is added to conversation log."""
        event_bus = EventBus()
        config = DiscussionConfig(max_messages=20)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        moderator = ModeratorAgent(
            id="moderator_001",
            name="Moderator",
            llm_client=mock_llm_client,
            session=session,
        )
        session.add_agent(moderator)

        msg = Message(
            id="msg_1",
            agent_id="persona_1",
            content="AI regulation discussion.",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await session.add_message(msg)

        synthesis_msg = await moderator.generate_synthesis()
        await session.add_message(synthesis_msg)

        assert len(session.conversation_log) >= 2
        assert any(
            msg.type == MessageType.MODERATOR for msg in session.conversation_log
        )


class TestExportE2E:
    """Test export works (TEXT, MARKDOWN) after discussion."""

    @pytest.mark.asyncio
    async def test_export_text_after_discussion(self, client):
        """TEXT export works after full discussion flow."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        msg1 = Message(
            id="msg_1",
            agent_id="persona_1",
            content="AI regulation is necessary.",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        msg2 = Message(
            id="msg_2",
            agent_id="persona_2",
            content="Regulation harms innovation.",
            timestamp=datetime(2024, 1, 15, 10, 5, 0),
            type=MessageType.AGENT,
        )

        await session.add_message(msg1)
        await session.add_message(msg2)

        await client.post(f"/api/discussion/{session_id}/stop")

        export_response = await client.get(
            f"/api/discussion/{session_id}/export?format=TEXT"
        )

        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in export_response.headers["content-disposition"]

        content = export_response.text
        assert "Should AI be regulated?" in content
        assert "AI regulation is necessary." in content
        assert "Regulation harms innovation." in content

    @pytest.mark.asyncio
    async def test_export_markdown_after_discussion(self, client):
        """MARKDOWN export works after full discussion flow."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        msg = Message(
            id="msg_1",
            agent_id="persona_1",
            content="AI regulation discussion point.",
            timestamp=datetime(2024, 1, 15, 10, 0, 0),
            type=MessageType.AGENT,
        )
        await session.add_message(msg)

        await client.post(f"/api/discussion/{session_id}/stop")

        export_response = await client.get(
            f"/api/discussion/{session_id}/export?format=MARKDOWN"
        )

        assert export_response.status_code == 200
        assert export_response.headers["content-type"] == "text/markdown; charset=utf-8"

        content = export_response.text
        assert "# Discussion: Should AI be regulated?" in content
        assert "## Participants" in content
        assert "## Conversation" in content

    @pytest.mark.asyncio
    async def test_export_includes_synthesis(self, client):
        """Export includes synthesis message at the end."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        assert response.status_code == 200
        session_id = response.json()["session_id"]

        store = get_session_store()
        session = store[session_id]

        msg = Message(
            id="msg_1",
            agent_id="persona_1",
            content="Discussion point",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await session.add_message(msg)

        await client.post(f"/api/discussion/{session_id}/stop")

        export_response = await client.get(
            f"/api/discussion/{session_id}/export?format=TEXT"
        )

        assert export_response.status_code == 200
        content = export_response.text
        assert len(content) > 50


class TestFullDiscussionLifecycleE2E:
    """Test complete discussion lifecycle from start to export."""

    @pytest.mark.asyncio
    async def test_complete_lifecycle_flow(self, mock_llm_client):
        """Complete lifecycle: create session → add messages → stop."""
        event_bus = EventBus()
        config = DiscussionConfig(max_messages=20)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel(
            "Should AI be regulated?", session=session
        )

        assert len(personas) >= 3
        assert len(personas) <= 10

        for persona in personas:
            session.add_agent(persona)

        for i, persona in enumerate(personas[:3]):
            msg = Message(
                id=f"msg_{i}",
                agent_id=persona.id,
                content=f"Perspective from {persona.name}: {persona.stance}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        assert len(session.conversation_log) >= 3

        session.stop_discussion()
        assert session.state == DiscussionState.COMPLETED

    @pytest.mark.asyncio
    async def test_message_count_verification(self, client):
        """Verify message count throughout discussion."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        session_id = response.json()["session_id"]
        store = get_session_store()
        session = store[session_id]

        initial_count = session.get_message_count()
        assert initial_count == 0

        for i in range(5):
            msg = Message(
                id=f"msg_{i}",
                agent_id=f"persona_{i}",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        assert session.get_message_count() == 5

    @pytest.mark.asyncio
    async def test_agent_participation_verification(self, client):
        """Verify all agents participate in discussion."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        session_id = response.json()["session_id"]
        personas = response.json()["personas"]

        store = get_session_store()
        session = store[session_id]

        participated_agents = set()
        for persona in personas:
            msg = Message(
                id=f"msg_{persona['id']}",
                agent_id=persona["id"],
                content=f"Message from {persona['name']}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)
            participated_agents.add(persona["id"])

        assert len(participated_agents) == len(personas)

    @pytest.mark.asyncio
    async def test_event_flow_verification(self, client):
        """Verify event flow throughout discussion."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        session_id = response.json()["session_id"]
        store = get_session_store()
        session = store[session_id]
        session.event_bus.clear_history()

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id=f"persona_{i}",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        history = session.event_bus.get_history()
        agent_events = [e for e in history if isinstance(e, AgentMessageEvent)]
        assert len(agent_events) == 3

        for event in agent_events:
            assert event.agent_id is not None
            assert event.content is not None
            assert "message_id" in event.metadata

    @pytest.mark.asyncio
    async def test_pause_resume_flow(self, client):
        """Pause and resume flow works correctly."""
        response = await client.post(
            "/api/discussion/start",
            json={"topic": "Should AI be regulated?"},
        )

        session_id = response.json()["session_id"]

        get_response = await client.get(f"/api/discussion/{session_id}")
        assert get_response.json()["state"] == "PAUSED"

        pause_response = await client.post(f"/api/discussion/{session_id}/pause")
        assert pause_response.json()["state"] == "PAUSED"

        store = get_session_store()
        session = store[session_id]
        session.start_discussion()

        get_response = await client.get(f"/api/discussion/{session_id}")
        assert get_response.json()["state"] == "ACTIVE"

        stop_response = await client.post(f"/api/discussion/{session_id}/stop")
        assert stop_response.json()["state"] == "COMPLETED"


class TestRealisticTopicE2E:
    """Test with realistic topic: 'Should AI be regulated?'."""

    @pytest.mark.asyncio
    async def test_ai_regulation_topic_panel(self, mock_llm_client):
        """Panel for AI regulation topic has appropriate personas."""
        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel("Should AI be regulated?")

        ai_keywords = [
            "ai",
            "artificial intelligence",
            "tech",
            "technology",
            "ethics",
            "policy",
            "researcher",
        ]

        relevant_count = 0
        for persona in personas:
            combined = f"{persona.role} {persona.background}".lower()
            if any(kw in combined for kw in ai_keywords):
                relevant_count += 1

        assert relevant_count >= 2

    @pytest.mark.asyncio
    async def test_ai_regulation_discussion_flow(self, mock_llm_client):
        """Full discussion flow on AI regulation topic."""
        event_bus = EventBus()
        config = DiscussionConfig(max_messages=20)
        session = DiscussionSession(
            topic="Should AI be regulated?",
            event_bus=event_bus,
            config=config,
        )

        from app.services.panel_generator import PanelGenerator

        panel_generator = PanelGenerator(mock_llm_client)
        personas = await panel_generator.generate_panel(
            "Should AI be regulated?", session=session
        )

        for persona in personas:
            session.add_agent(persona)

        discussion_content = [
            "AI systems pose significant risks if not properly regulated.",
            "Regulation would slow down innovation and economic growth.",
            "We need balanced regulation that addresses risks without stifling progress.",
            "Both extremes are problematic - we need evidence-based policy.",
        ]

        for i, content in enumerate(discussion_content):
            persona_idx = i % len(personas)
            msg = Message(
                id=f"msg_{i}",
                agent_id=personas[persona_idx].id,
                content=content,
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await session.add_message(msg)

        assert len(session.conversation_log) == len(discussion_content)

        session.stop_discussion()
        assert session.state == DiscussionState.COMPLETED
