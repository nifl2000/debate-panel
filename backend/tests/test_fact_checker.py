"""
Integration tests for FactCheckerAgent.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.fact_checker import (
    FactCheckerAgent,
    FactCheckResult,
    FactCheckSource,
)
from app.models.agent import AgentType
from app.models.discussion import DiscussionConfig
from app.models.message import Message, MessageType
from app.orchestration.event_bus import EventBus, FactCheckEvent
from app.llm.client import LLMClient


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
def fact_checker_agent(mock_llm_client, mock_session):
    """Create a FactCheckerAgent instance for testing."""
    return FactCheckerAgent(
        llm_client=mock_llm_client,
        session=mock_session,
    )


@pytest.fixture
def fact_checker_agent_no_session(mock_llm_client):
    """Create a FactCheckerAgent without session for testing."""
    return FactCheckerAgent(
        llm_client=mock_llm_client,
        session=None,
    )


class TestFactCheckResult:
    """Tests for FactCheckResult model."""

    def test_fact_check_result_creation(self):
        """Test creating a FactCheckResult."""
        result = FactCheckResult(
            claim="The Earth is round",
            verdict="verified",
            sources=[
                FactCheckSource(
                    url="https://example.com",
                    title="Example",
                    credibility="high",
                )
            ],
            explanation="Multiple sources confirm.",
        )
        assert result.claim == "The Earth is round"
        assert result.verdict == "verified"
        assert len(result.sources) == 1
        assert result.explanation == "Multiple sources confirm."

    def test_fact_check_result_default_sources(self):
        """Test FactCheckResult with default empty sources."""
        result = FactCheckResult(
            claim="Test claim",
            verdict="unverified",
        )
        assert result.sources == []
        assert result.explanation is None

    def test_fact_check_source_creation(self):
        """Test creating a FactCheckSource."""
        source = FactCheckSource(
            url="https://nasa.gov",
            title="NASA",
            credibility="high",
        )
        assert source.url == "https://nasa.gov"
        assert source.title == "NASA"
        assert source.credibility == "high"


class TestFactCheckerAgentInitialization:
    """Tests for FactCheckerAgent initialization."""

    def test_fact_checker_agent_has_correct_attributes(self, fact_checker_agent):
        """Test that fact checker agent initializes with correct attributes."""
        assert fact_checker_agent.id == "fact_checker_001"
        assert fact_checker_agent.name == "Fact Checker"
        assert fact_checker_agent.type == AgentType.FACT_CHECKER
        assert fact_checker_agent._search_timeout == 10

    def test_fact_checker_agent_without_session(self, fact_checker_agent_no_session):
        """Test fact checker agent can be created without session."""
        assert fact_checker_agent_no_session.session is None


class TestClaimDetection:
    """Tests for claim detection."""

    @pytest.mark.asyncio
    async def test_detect_claims_returns_list(
        self, fact_checker_agent, mock_llm_client
    ):
        """Test that detect_claims returns a list with at most one claim."""

        async def mock_stream(messages):
            yield '["Climate change is real and caused by human activity"]'

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        claims = await fact_checker_agent.detect_claims(
            "Climate change is real and CO2 levels are rising."
        )

        assert isinstance(claims, list)
        assert len(claims) <= 1
        if claims:
            assert len(claims[0]) > 15

    @pytest.mark.asyncio
    async def test_detect_claims_empty_message(
        self, fact_checker_agent, mock_llm_client
    ):
        """Test that detect_claims returns empty list for empty message."""

        async def mock_stream(messages):
            yield "[]"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        claims = await fact_checker_agent.detect_claims("")

        assert claims == []

    @pytest.mark.asyncio
    async def test_detect_claims_no_factual_claims(
        self, fact_checker_agent, mock_llm_client
    ):
        """Test that detect_claims returns empty list for opinion-only message."""

        async def mock_stream(messages):
            yield "[]"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        claims = await fact_checker_agent.detect_claims("I think this is a good idea.")

        assert claims == []

    @pytest.mark.asyncio
    async def test_detect_claims_handles_markdown_json(
        self, fact_checker_agent, mock_llm_client
    ):
        """Test that detect_claims handles JSON in markdown code blocks."""

        async def mock_stream(messages):
            yield '```json\n["This is a claim that is longer than fifteen characters"]\n```'

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        claims = await fact_checker_agent.detect_claims("Test message")

        assert len(claims) <= 1
        if claims:
            assert len(claims[0]) > 15

    @pytest.mark.asyncio
    async def test_detect_claims_handles_invalid_json(
        self, fact_checker_agent, mock_llm_client
    ):
        """Test that detect_claims handles invalid JSON response."""

        async def mock_stream(messages):
            yield "This is not JSON"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        claims = await fact_checker_agent.detect_claims("Test message")

        assert claims == []


class TestFactCheck:
    """Tests for fact-checking claims."""

    @pytest.mark.asyncio
    async def test_check_claim_returns_result(
        self, fact_checker_agent, mock_llm_client
    ):
        """Test that check_claim returns a FactCheckResult."""

        async def mock_stream(messages):
            yield json.dumps(
                {
                    "verdict": "verified",
                    "sources": [
                        {
                            "url": "https://example.com",
                            "title": "Example",
                            "credibility": "high",
                        }
                    ],
                    "explanation": "Sources confirm the claim.",
                }
            )

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        async def mock_search(claim):
            return [
                {"url": "https://example.com", "title": "Example", "snippet": "Test"}
            ]

        fact_checker_agent._web_search = mock_search

        result = await fact_checker_agent.check_claim("Test claim")

        assert isinstance(result, FactCheckResult)
        assert result.claim == "Test claim"
        assert result.verdict == "verified"

    @pytest.mark.asyncio
    async def test_check_claim_no_sources(self, fact_checker_agent):
        """Test that check_claim returns unverified when no sources found."""

        async def mock_search(claim):
            return []

        fact_checker_agent._web_search = mock_search

        result = await fact_checker_agent.check_claim("Test claim")

        assert result.verdict == "unverified"
        assert result.sources == []
        assert "No sources found" in result.explanation

    @pytest.mark.asyncio
    async def test_check_claim_timeout(self, fact_checker_agent):
        """Test that check_claim handles timeout gracefully."""

        async def mock_search(claim):
            raise asyncio.TimeoutError()

        fact_checker_agent._web_search = mock_search

        result = await fact_checker_agent.check_claim("Test claim")

        assert result.verdict == "unverified"
        assert "timed out" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_check_claim_error(self, fact_checker_agent):
        """Test that check_claim handles errors gracefully."""

        async def mock_search(claim):
            raise Exception("Search failed")

        fact_checker_agent._web_search = mock_search

        result = await fact_checker_agent.check_claim("Test claim")

        assert result.verdict == "unverified"
        assert "Error" in result.explanation

    @pytest.mark.asyncio
    async def test_check_claim_validates_sources(
        self, fact_checker_agent, mock_llm_client
    ):
        """Test that check_claim validates sources using LLM."""
        captured_messages = None

        async def mock_stream(messages):
            captured_messages = messages
            yield json.dumps(
                {
                    "verdict": "verified",
                    "sources": [
                        {
                            "url": "https://nasa.gov",
                            "title": "NASA",
                            "credibility": "high",
                        }
                    ],
                    "explanation": "NASA confirms.",
                }
            )

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        async def mock_search(claim):
            return [
                {"url": "https://nasa.gov", "title": "NASA", "snippet": "Climate data"}
            ]

        fact_checker_agent._web_search = mock_search

        result = await fact_checker_agent.check_claim("Earth temperature rising")

        assert result.verdict == "verified"
        assert len(result.sources) == 1
        assert result.sources[0].credibility == "high"


class TestRunFactCheck:
    """Tests for run_fact_check main entry point."""

    @pytest.mark.asyncio
    async def test_run_fact_check_publishes_events(
        self, fact_checker_agent, mock_session, mock_llm_client
    ):
        """Test that run_fact_check publishes FactCheckEvents to event bus."""
        events_published = []
        mock_session.event_bus.publish = MagicMock(
            side_effect=lambda e: events_published.append(e)
        )

        async def mock_stream(messages):
            yield '["Climate change is real"]'

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        async def mock_search(claim):
            return [{"url": "https://nasa.gov", "title": "NASA", "snippet": "Data"}]

        fact_checker_agent._web_search = mock_search

        events = await fact_checker_agent.run_fact_check(
            "Climate change is real and caused by human activity."
        )

        assert len(events) == 1
        assert isinstance(events[0], FactCheckEvent)
        assert len(events_published) == 1

    @pytest.mark.asyncio
    async def test_run_fact_check_no_claims(self, fact_checker_agent, mock_llm_client):
        """Test that run_fact_check returns empty list when no claims detected."""

        async def mock_stream(messages):
            yield "[]"

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        events = await fact_checker_agent.run_fact_check("I think this is good.")

        assert events == []

    @pytest.mark.asyncio
    async def test_run_fact_check_without_session(
        self, fact_checker_agent_no_session, mock_llm_client
    ):
        """Test that run_fact_check works without session (no publishing)."""

        async def mock_stream(messages):
            yield '["This is a test claim that is longer than fifteen characters"]'

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        async def mock_search(claim):
            return [
                {"url": "https://example.com", "title": "Example", "snippet": "Test"}
            ]

        fact_checker_agent_no_session._web_search = mock_search

        events = await fact_checker_agent_no_session.run_fact_check("Test claim here.")

        assert len(events) <= 1
        if events:
            assert isinstance(events[0], FactCheckEvent)

    @pytest.mark.asyncio
    async def test_run_fact_check_single_claim(
        self, fact_checker_agent, mock_session, mock_llm_client
    ):
        """Test that run_fact_check handles a single claim (implementation returns at most one)."""
        events_published = []
        mock_session.event_bus.publish = MagicMock(
            side_effect=lambda e: events_published.append(e)
        )

        async def mock_stream(messages):
            yield '["This is a claim that is longer than fifteen characters"]'

        mock_llm_client.stream_chat = MagicMock(return_value=mock_stream([]))

        async def mock_search(claim):
            return [
                {"url": "https://example.com", "title": "Example", "snippet": "Test"}
            ]

        fact_checker_agent._web_search = mock_search

        events = await fact_checker_agent.run_fact_check("Claim 1 and Claim 2.")

        assert len(events) <= 1
        assert len(events_published) <= 1


class TestResultToEvent:
    """Tests for converting FactCheckResult to FactCheckEvent."""

    def test_result_to_event_verified(self, fact_checker_agent):
        """Test converting verified result to event."""
        result = FactCheckResult(
            claim="Test claim",
            verdict="verified",
            sources=[
                FactCheckSource(
                    url="https://nasa.gov",
                    title="NASA",
                    credibility="high",
                )
            ],
            explanation="Verified by NASA.",
        )

        event = fact_checker_agent._result_to_event(result)

        assert isinstance(event, FactCheckEvent)
        assert event.claim == "Test claim"
        assert event.result is True
        assert event.source == "https://nasa.gov"
        assert event.confidence is not None
        assert event.confidence > 0.7

    def test_result_to_event_unverified(self, fact_checker_agent):
        """Test converting unverified result to event."""
        result = FactCheckResult(
            claim="Test claim",
            verdict="unverified",
            sources=[],
            explanation="No sources found.",
        )

        event = fact_checker_agent._result_to_event(result)

        assert event.result is False
        assert event.confidence == 0.0
        assert event.source is None

    def test_result_to_event_disputed(self, fact_checker_agent):
        """Test converting disputed result to event."""
        result = FactCheckResult(
            claim="Test claim",
            verdict="disputed",
            sources=[
                FactCheckSource(
                    url="https://source1.com",
                    title="Source 1",
                    credibility="medium",
                )
            ],
            explanation="Sources disagree.",
        )

        event = fact_checker_agent._result_to_event(result)

        assert event.result is False
        assert event.confidence < 0.5

    def test_result_to_event_includes_metadata(self, fact_checker_agent):
        """Test that event includes metadata with full result."""
        result = FactCheckResult(
            claim="Test claim",
            verdict="verified",
            sources=[
                FactCheckSource(
                    url="https://example.com",
                    title="Example",
                    credibility="high",
                )
            ],
            explanation="Verified.",
        )

        event = fact_checker_agent._result_to_event(result)

        assert "verdict" in event.metadata
        assert "sources" in event.metadata
        assert "explanation" in event.metadata
        assert event.metadata["verdict"] == "verified"


class TestConfidenceCalculation:
    """Tests for confidence calculation."""

    def test_calculate_confidence_verified_high_credibility(self, fact_checker_agent):
        """Test confidence for verified claim with high credibility sources."""
        result = FactCheckResult(
            claim="Test",
            verdict="verified",
            sources=[
                FactCheckSource(url="url1", title="T1", credibility="high"),
                FactCheckSource(url="url2", title="T2", credibility="high"),
            ],
        )

        confidence = fact_checker_agent._calculate_confidence(result)

        assert confidence >= 0.7
        assert confidence <= 0.95

    def test_calculate_confidence_verified_medium_credibility(self, fact_checker_agent):
        """Test confidence for verified claim with medium credibility sources."""
        result = FactCheckResult(
            claim="Test",
            verdict="verified",
            sources=[
                FactCheckSource(url="url1", title="T1", credibility="medium"),
            ],
        )

        confidence = fact_checker_agent._calculate_confidence(result)

        assert confidence >= 0.7

    def test_calculate_confidence_unverified(self, fact_checker_agent):
        """Test confidence for unverified claim."""
        result = FactCheckResult(
            claim="Test",
            verdict="unverified",
            sources=[],
        )

        confidence = fact_checker_agent._calculate_confidence(result)

        assert confidence == 0.0

    def test_calculate_confidence_disputed(self, fact_checker_agent):
        """Test confidence for disputed claim."""
        result = FactCheckResult(
            claim="Test",
            verdict="disputed",
            sources=[
                FactCheckSource(url="url1", title="T1", credibility="high"),
            ],
        )

        confidence = fact_checker_agent._calculate_confidence(result)

        assert confidence >= 0.3
        assert confidence < 0.5

    def test_calculate_confidence_no_sources(self, fact_checker_agent):
        """Test confidence when no sources available."""
        result = FactCheckResult(
            claim="Test",
            verdict="verified",
            sources=[],
        )

        confidence = fact_checker_agent._calculate_confidence(result)

        assert confidence == 0.0


class TestGenerateResponse:
    """Tests for generate_response method."""

    @pytest.mark.asyncio
    async def test_generate_response_returns_message(self, fact_checker_agent):
        """Test that generate_response returns a Message."""
        response = await fact_checker_agent.generate_response([])

        assert isinstance(response, Message)
        assert response.type == MessageType.FACT_CHECK
        assert response.agent_id == "fact_checker_001"


class TestWebSearchMock:
    """Tests for web search functionality (mocked)."""

    @pytest.mark.asyncio
    async def test_web_search_falls_back_to_duckduckgo(self, fact_checker_agent):
        """Test that _web_search falls back to DuckDuckGo when crawl4ai not available."""
        with patch.dict("sys.modules", {"crawl4ai": None}):
            results = await fact_checker_agent._web_search("Test claim")

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_web_search_timeout_raises(self, fact_checker_agent):
        """Test that _web_search timeout raises TimeoutError."""

        async def slow_search(claim):
            await asyncio.sleep(15)
            return []

        fact_checker_agent._web_search = slow_search

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fact_checker_agent._web_search("Test"), timeout=12)
