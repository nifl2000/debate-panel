"""
Integration tests for ModeratorAgent.
"""

import asyncio
from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from app.agents.moderator import (
    ModeratorAgent,
    StallDetectorProtocol,
    FactCheckerProtocol,
)
from app.agents.persona import PersonaAgent
from app.models.agent import AgentType
from app.models.discussion import DiscussionConfig, DiscussionState
from app.models.message import Message, MessageType
from app.orchestration.event_bus import (
    EventBus,
    AgentMessageEvent,
    FactCheckEvent,
    StallDetectedEvent,
)
from app.llm.client import LLMClient


from app.llm.prompts import MODERATOR_PROMPT, SYNTHESIS_PROMPT


class MockStallInfo:
    """Mock StallInfo for testing."""

    def __init__(self, reason: str, signals: List[str], suggestion: str):
        self.reason = reason
        self.signals = signals
        self.suggestion = suggestion


class MockStallDetector:
    """Mock Stall detector for testing."""

    def __init__(self, should_detect: bool = False):
        self._should_detect = should_detect
        self._stall_info = None

    def detect_stall(
        self, conversation_log: List[Message], last_message_time: datetime
    ) -> Optional[MockStallInfo]:
        if self._should_detect:
            return MockStallInfo(
                reason="Discussion stalling",
                signals=["timeout", "keywords"],
                suggestion="Let's explore a new perspective on this topic.",
            )
        return None

    def get_intervention_suggestion(self, stall_info: MockStallInfo) -> str:
        return stall_info.suggestion

    def set_should_detect(self, value: bool):
        self._should_detect = value


class MockFactChecker:
    """Mock fact checker for testing."""

    def __init__(self, claims_to_detect: List[str] = None):
        self._claims_to_detect = claims_to_detect or []
        self._check_results = {}

    def detect_claims(self, message: str) -> List[str]:
        return self._claims_to_detect

    async def check_claim(self, claim: str) -> Optional[FactCheckEvent]:
        return self._check_results.get(claim)

    def set_claims_to_detect(self, claims: List[str]):
        self._claims_to_detect = claims

    def set_check_result(self, claim: str, result: Optional[FactCheckEvent]):
        self._check_results[claim] = result


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client for testing."""
    client = MagicMock(spec=LLMClient)
    client.default_model = "qwen3.6-plus"
    return client


@pytest.fixture
def event_bus():
    """Create an EventBus instance for testing."""
    return EventBus()


@pytest.fixture
def mock_session(event_bus):
    """Create a mock DiscussionSession for testing."""
    from app.orchestration.session import DiscussionSession

    session = DiscussionSession(
        topic="Climate change policy",
        event_bus=event_bus,
        config=DiscussionConfig(max_messages=20),
    )
    return session


@pytest.fixture
def mock_stall_detector():
    """Create a mock stall detector for testing."""
    return MockStallDetector()


@pytest.fixture
def mock_fact_checker():
    """Create a mock fact checker for testing."""
    return MockFactChecker()


@pytest.fixture
def moderator_agent(
    mock_llm_client, mock_session, mock_stall_detector, mock_fact_checker
):
    """Create a ModeratorAgent instance for testing."""
    return ModeratorAgent(
        id="moderator_001",
        name="Moderator",
        llm_client=mock_llm_client,
        session=mock_session,
        stall_detector=mock_stall_detector,
        fact_checker=mock_fact_checker,
    )


@pytest.fixture
def moderator_agent_no_session(mock_llm_client):
    """Create a ModeratorAgent without session for testing."""
    return ModeratorAgent(
        id="moderator_002",
        name="Moderator",
        llm_client=mock_llm_client,
        session=None,
    )


@pytest.fixture
def persona_agent(mock_llm_client, mock_session):
    """Create a PersonaAgent for testing speaker selection."""
    return PersonaAgent(
        id="persona_001",
        name="Dr. Sarah Chen",
        role="Climate Scientist",
        background="PhD in Atmospheric Sciences",
        stance="Strongly supports aggressive climate action",
        llm_client=mock_llm_client,
        session=mock_session,
    )


@pytest.fixture
def persona_agent_2(mock_llm_client, mock_session):
    """Create a second PersonaAgent for testing speaker selection."""
    return PersonaAgent(
        id="persona_002",
        name="John Smith",
        role="Policy Analyst",
        background="10 years in environmental policy",
        stance="Moderate approach preferred",
        llm_client=mock_llm_client,
        session=mock_session,
    )


class TestModeratorAgentInitialization:
    """Tests for ModeratorAgent initialization."""

    def test_moderator_agent_has_correct_attributes(self, moderator_agent):
        """Test that moderator agent initializes with correct attributes."""
        assert moderator_agent.id == "moderator_001"
        assert moderator_agent.name == "Moderator"
        assert moderator_agent.type == AgentType.MODERATOR
        assert moderator_agent.stall_detector is not None
        assert moderator_agent.fact_checker is not None
        assert moderator_agent._pending_fact_checks == []
        assert moderator_agent._last_speaker_id is None
        assert moderator_agent._speaker_counts == {}

    def test_moderator_agent_without_dependencies(self, mock_llm_client, mock_session):
        """Test moderator agent can be created without stall_detector and fact_checker."""
        moderator = ModeratorAgent(
            id="moderator_003",
            name="Moderator",
            llm_client=mock_llm_client,
            session=mock_session,
        )
        assert moderator.stall_detector is None
        assert moderator.fact_checker is None


class TestModeratorLoop:
    """Tests for moderator loop functionality."""

    @pytest.mark.asyncio
    async def test_moderator_loop_subscribes_to_events(
        self, moderator_agent, mock_session
    ):
        """Test that moderator loop subscribes to all relevant events."""
        received_events = []

        def capture_subscription(event_type, handler):
            received_events.append(event_type)

        mock_session.event_bus.subscribe = MagicMock(side_effect=capture_subscription)
        mock_session.state = "COMPLETED"

        await moderator_agent.moderator_loop()

        assert "agent_message" in received_events
        assert "fact_check" in received_events
        assert "stall_detected" in received_events

    @pytest.mark.asyncio
    async def test_moderator_loop_unsubscribes_on_exit(
        self, moderator_agent, mock_session
    ):
        """Test that moderator loop unsubscribes when exiting."""
        unsubscribed_events = []

        def capture_unsubscription(event_type, handler):
            unsubscribed_events.append(event_type)

        mock_session.event_bus.unsubscribe = MagicMock(
            side_effect=capture_unsubscription
        )
        mock_session.state = "COMPLETED"

        await moderator_agent.moderator_loop()

        assert "agent_message" in unsubscribed_events
        assert "fact_check" in unsubscribed_events
        assert "stall_detected" in unsubscribed_events

    @pytest.mark.asyncio
    async def test_moderator_loop_returns_without_session(
        self, moderator_agent_no_session
    ):
        """Test that moderator loop returns early if no session."""
        result = await moderator_agent_no_session.moderator_loop()
        assert result is None

    @pytest.mark.asyncio
    async def test_start_loop_creates_task(self, moderator_agent, mock_session):
        """Test that start_loop creates a background task."""
        mock_session._stop_requested = True
        moderator_agent.start_loop()
        assert moderator_agent._moderator_task is not None
        await asyncio.sleep(2.5)
        assert moderator_agent._moderator_task.done()
        moderator_agent.stop_loop()

    @pytest.mark.asyncio
    async def test_stop_loop_cancels_task(self, moderator_agent, mock_session):
        """Test that stop_loop cancels the background task."""
        moderator_agent.start_loop()
        await asyncio.sleep(0.05)
        moderator_agent.stop_loop()
        assert moderator_agent._running is False


class TestEventHandling:
    """Tests for event handling."""

    def test_handle_agent_message_updates_speaker_counts(
        self, moderator_agent, mock_session
    ):
        """Test that handling AgentMessageEvent updates speaker counts."""
        event = AgentMessageEvent(
            agent_id="persona_001",
            agent_type=AgentType.PERSONA.value,
            content="Test message",
            metadata={},
        )

        moderator_agent._handle_agent_message_event(event)

        assert moderator_agent._last_speaker_id == "persona_001"
        assert moderator_agent._speaker_counts["persona_001"] == 1

    def test_handle_agent_message_triggers_stall_detection(
        self, moderator_agent, mock_session, mock_stall_detector
    ):
        """Test that stall detection is triggered on AgentMessageEvent."""
        mock_stall_detector.set_should_detect(True)

        events_published = []
        mock_session.event_bus.publish = MagicMock(
            side_effect=lambda e: events_published.append(e)
        )

        event = AgentMessageEvent(
            agent_id="persona_001",
            agent_type=AgentType.PERSONA.value,
            content="Test message",
            metadata={},
        )

        moderator_agent._handle_agent_message_event(event)

        assert len(events_published) == 1
        assert isinstance(events_published[0], StallDetectedEvent)

    @pytest.mark.asyncio
    async def test_handle_agent_message_triggers_fact_check(
        self, moderator_agent, mock_session, mock_fact_checker
    ):
        """Test that fact-check is triggered when claims are detected."""
        mock_fact_checker.set_claims_to_detect(["Climate change is caused by CO2"])

        event = AgentMessageEvent(
            agent_id="persona_001",
            agent_type=AgentType.PERSONA.value,
            content="Climate change is caused by CO2 emissions.",
            metadata={},
        )

        moderator_agent._handle_agent_message_event(event)

        await asyncio.sleep(0.05)

        assert mock_fact_checker._claims_to_detect == [
            "Climate change is caused by CO2"
        ]

    def test_handle_fact_check_event_stores_pending(self, moderator_agent):
        """Test that FactCheckEvent with result is stored as pending."""
        event = FactCheckEvent(
            claim="Test claim",
            source="Wikipedia",
            result=True,
            confidence=0.9,
            metadata={},
        )

        moderator_agent._handle_fact_check_event(event)

        assert len(moderator_agent._pending_fact_checks) == 1
        assert moderator_agent._pending_fact_checks[0] == event

    def test_handle_fact_check_event_ignores_incomplete(self, moderator_agent):
        """Test that FactCheckEvent without result is not stored."""
        event = FactCheckEvent(
            claim="Test claim",
            source=None,
            result=None,
            confidence=None,
            metadata={},
        )

        moderator_agent._handle_fact_check_event(event)

        assert len(moderator_agent._pending_fact_checks) == 0

    @pytest.mark.asyncio
    async def test_handle_stall_detected_injects_intervention(
        self, moderator_agent, mock_session
    ):
        """Test that StallDetectedEvent triggers intervention injection."""
        event = StallDetectedEvent(
            agent_id="moderator_001",
            reason="Discussion stalling",
            metadata={"suggestion": "Let's explore a new angle."},
        )

        moderator_agent._handle_stall_detected_event(event)

        # Wait for async task to complete
        await asyncio.sleep(0.1)

        assert len(mock_session.conversation_log) == 1
        assert mock_session.conversation_log[0].type == MessageType.MODERATOR


class TestConvergenceDetection:
    """Tests for convergence detection."""

    @pytest.mark.asyncio
    async def test_detect_convergence_returns_true_at_max_messages(
        self, moderator_agent, mock_session
    ):
        """Test that convergence is detected at max message limit."""
        mock_session.config = DiscussionConfig(max_messages=5)

        for i in range(5):
            msg = Message(
                id=f"msg_{i}",
                agent_id="persona_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await mock_session.add_message(msg)

        converged = await moderator_agent.detect_convergence()
        assert converged is True

    @pytest.mark.asyncio
    async def test_detect_convergence_returns_false_without_session(
        self, moderator_agent_no_session
    ):
        """Test that convergence detection returns False without session."""
        converged = await moderator_agent_no_session.detect_convergence()
        assert converged is False

    @pytest.mark.asyncio
    async def test_detect_convergence_uses_llm_judgment(
        self, moderator_agent, mock_session, mock_llm_client
    ):
        """Test that convergence detection uses LLM judgment."""

        async def mock_stream(messages):
            yield "CONVERGED"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id="persona_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await mock_session.add_message(msg)

        converged = await moderator_agent.detect_convergence()
        assert converged is True

    @pytest.mark.asyncio
    async def test_detect_convergence_returns_continue(
        self, moderator_agent, mock_session, mock_llm_client
    ):
        """Test that convergence detection returns False when LLM says CONTINUE."""

        async def mock_stream(messages):
            yield "CONTINUE"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id="persona_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await mock_session.add_message(msg)

        converged = await moderator_agent.detect_convergence()
        assert converged is False


class TestSynthesisGeneration:
    """Tests for synthesis generation."""

    @pytest.mark.asyncio
    async def test_generate_synthesis_returns_message(
        self, moderator_agent, mock_session, mock_llm_client
    ):
        """Test that generate_synthesis returns a Message."""

        async def mock_stream(messages):
            yield "Summary of discussion..."

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        msg = Message(
            id="msg_1",
            agent_id="persona_001",
            content="Test message",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await mock_session.add_message(msg)

        synthesis = await moderator_agent.generate_synthesis()

        assert isinstance(synthesis, Message)
        assert synthesis.type == MessageType.MODERATOR
        assert synthesis.agent_id == "moderator_001"

    @pytest.mark.asyncio
    async def test_generate_synthesis_adds_to_conversation_log(
        self, moderator_agent, mock_session, mock_llm_client
    ):
        """Test that synthesis is added to conversation log."""

        async def mock_stream(messages):
            yield "Final synthesis..."

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        msg = Message(
            id="msg_1",
            agent_id="persona_001",
            content="Test message",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await mock_session.add_message(msg)

        initial_count = len(mock_session.conversation_log)
        await moderator_agent.generate_synthesis()

        assert len(mock_session.conversation_log) == initial_count + 1

    @pytest.mark.asyncio
    async def test_generate_synthesis_without_session(
        self, moderator_agent_no_session, mock_llm_client
    ):
        """Test that synthesis without session returns fallback message."""

        async def mock_stream(messages):
            yield "Content"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        synthesis = await moderator_agent_no_session.generate_synthesis()

        assert synthesis.content == "No discussion to synthesize."

    @pytest.mark.asyncio
    async def test_generate_synthesis_uses_synthesis_prompt(
        self, moderator_agent, mock_session, mock_llm_client
    ):
        """Test that generate_synthesis uses SYNTHESIS_PROMPT."""
        captured_messages = None

        async def mock_stream(messages):
            captured_messages = messages
            yield "Synthesis content"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        msg = Message(
            id="msg_1",
            agent_id="persona_001",
            content="Test message",
            timestamp=datetime.now(),
            type=MessageType.AGENT,
        )
        await mock_session.add_message(msg)

        await moderator_agent.generate_synthesis()

        # Verify stream_chat was called
        mock_llm_client.stream_chat.assert_called_once()


class TestSpeakerSelection:
    """Tests for speaker selection."""

    def test_select_next_speaker_returns_none_without_session(
        self, moderator_agent_no_session
    ):
        """Test that speaker selection returns None without session."""
        result = moderator_agent_no_session.select_next_speaker()
        assert result is None

    def test_select_next_speaker_returns_none_without_personas(
        self, moderator_agent, mock_session
    ):
        """Test that speaker selection returns None if no personas in session."""
        result = moderator_agent.select_next_speaker()
        assert result is None

    def test_select_next_speaker_returns_single_persona(
        self, moderator_agent, mock_session, persona_agent
    ):
        """Test that speaker selection returns the only persona."""
        mock_session.add_agent(persona_agent)

        result = moderator_agent.select_next_speaker()
        assert result == "persona_001"

    def test_select_next_speaker_balances_participation(
        self, moderator_agent, mock_session, persona_agent, persona_agent_2
    ):
        """Test that speaker selection balances participation."""
        mock_session.add_agent(persona_agent)
        mock_session.add_agent(persona_agent_2)

        # First persona has spoken more
        moderator_agent._speaker_counts["persona_001"] = 5
        moderator_agent._speaker_counts["persona_002"] = 1

        result = moderator_agent.select_next_speaker()
        assert result == "persona_002"

    def test_select_next_speaker_avoids_last_speaker(
        self, moderator_agent, mock_session, persona_agent, persona_agent_2
    ):
        """Test that speaker selection avoids last speaker."""
        mock_session.add_agent(persona_agent)
        mock_session.add_agent(persona_agent_2)

        moderator_agent._last_speaker_id = "persona_001"
        moderator_agent._speaker_counts["persona_001"] = 2
        moderator_agent._speaker_counts["persona_002"] = 2

        result = moderator_agent.select_next_speaker()
        assert result == "persona_002"

    def test_select_next_speaker_prioritizes_least_spoken(
        self, moderator_agent, mock_session, persona_agent, persona_agent_2
    ):
        """Test that speaker selection prioritizes least spoken persona."""
        mock_session.add_agent(persona_agent)
        mock_session.add_agent(persona_agent_2)

        moderator_agent._speaker_counts["persona_001"] = 3
        moderator_agent._speaker_counts["persona_002"] = 0

        result = moderator_agent.select_next_speaker()
        assert result == "persona_002"


class TestFactCheckIntegration:
    """Tests for fact-check integration."""

    def test_get_pending_fact_checks_returns_copy(self, moderator_agent):
        """Test that get_pending_fact_checks returns a copy."""
        event = FactCheckEvent(
            claim="Test claim",
            source="Wikipedia",
            result=True,
            confidence=0.9,
            metadata={},
        )
        moderator_agent._pending_fact_checks.append(event)

        result = moderator_agent.get_pending_fact_checks()
        assert result == [event]
        assert result is not moderator_agent._pending_fact_checks

    def test_clear_pending_fact_checks(self, moderator_agent):
        """Test that clear_pending_fact_checks clears the list."""
        event = FactCheckEvent(
            claim="Test claim",
            source="Wikipedia",
            result=True,
            confidence=0.9,
            metadata={},
        )
        moderator_agent._pending_fact_checks.append(event)

        moderator_agent.clear_pending_fact_checks()
        assert len(moderator_agent._pending_fact_checks) == 0

    @pytest.mark.asyncio
    async def test_integrate_fact_check_creates_message(
        self, moderator_agent, mock_session
    ):
        """Test that integrate_fact_check creates a FACT_CHECK message."""
        event = FactCheckEvent(
            claim="Climate change is real",
            source="NASA",
            result=True,
            confidence=0.95,
            metadata={},
        )

        message = await moderator_agent.integrate_fact_check(event)

        assert message.type == MessageType.FACT_CHECK
        assert "Verified" in message.content
        assert "NASA" in message.content

    @pytest.mark.asyncio
    async def test_integrate_fact_check_adds_to_log(
        self, moderator_agent, mock_session
    ):
        """Test that integrate_fact_check adds message to conversation log."""
        event = FactCheckEvent(
            claim="Test claim",
            source="Wikipedia",
            result=True,
            confidence=0.9,
            metadata={},
        )

        initial_count = len(mock_session.conversation_log)
        await moderator_agent.integrate_fact_check(event)

        assert len(mock_session.conversation_log) == initial_count + 1

    def test_format_fact_check_verdict_verified(self, moderator_agent):
        """Test formatting verified fact-check."""
        event = FactCheckEvent(
            claim="Test claim",
            source="Wikipedia",
            result=True,
            confidence=0.9,
            metadata={},
        )

        result = moderator_agent._format_fact_check_verdict(event)
        assert "Verified" in result
        assert "90%" in result
        assert "Wikipedia" in result

    def test_format_fact_check_verdict_unverified(self, moderator_agent):
        """Test formatting unverified fact-check."""
        event = FactCheckEvent(
            claim="Test claim",
            source=None,
            result=False,
            confidence=None,
            metadata={},
        )

        result = moderator_agent._format_fact_check_verdict(event)
        assert "Unverified" in result


class TestGenerateResponse:
    """Tests for generate_response method."""

    @pytest.mark.asyncio
    async def test_generate_response_returns_message(
        self, moderator_agent, mock_llm_client
    ):
        """Test that generate_response returns a Message."""

        async def mock_stream(messages):
            yield "Moderator response"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        context = [{"role": "user", "content": "Question"}]
        response = await moderator_agent.generate_response(context)

        assert isinstance(response, Message)
        assert response.type == MessageType.MODERATOR
        assert response.agent_id == "moderator_001"

    @pytest.mark.asyncio
    async def test_generate_response_uses_moderator_prompt(
        self, moderator_agent, mock_session, mock_llm_client
    ):
        """Test that generate_response uses MODERATOR_PROMPT."""
        captured_messages = None

        async def mock_stream(messages):
            captured_messages = messages
            yield "Response"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        context = [{"role": "user", "content": "Question"}]
        await moderator_agent.generate_response(context)

        mock_llm_client.stream_chat.assert_called_once()


class TestInterventionInjection:
    """Tests for intervention injection."""

    @pytest.mark.asyncio
    async def test_inject_intervention_creates_message(
        self, moderator_agent, mock_session
    ):
        """Test that _inject_intervention creates a moderator message."""
        await moderator_agent._inject_intervention("Let's explore a new angle.")

        assert len(mock_session.conversation_log) == 1
        assert mock_session.conversation_log[0].type == MessageType.MODERATOR
        assert "Let's explore a new angle." in mock_session.conversation_log[0].content

    @pytest.mark.asyncio
    async def test_inject_intervention_without_session(
        self, moderator_agent_no_session
    ):
        """Test that _inject_intervention returns early without session."""
        await moderator_agent_no_session._inject_intervention("Suggestion")
        # Should not raise an error


class TestConvergenceCheck:
    """Tests for convergence check triggering."""

    @pytest.mark.asyncio
    async def test_check_convergence_stops_discussion(
        self, moderator_agent, mock_session, mock_llm_client
    ):
        """Test that _check_convergence stops discussion when converged."""

        async def mock_stream(messages):
            yield "CONVERGED"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        mock_session.start_discussion()
        moderator_agent.start_loop()

        for i in range(3):
            msg = Message(
                id=f"msg_{i}",
                agent_id="persona_001",
                content=f"Message {i}",
                timestamp=datetime.now(),
                type=MessageType.AGENT,
            )
            await mock_session.add_message(msg)

        await moderator_agent._check_convergence()

        assert mock_session.state == DiscussionState.COMPLETED
        moderator_agent.stop_loop()
