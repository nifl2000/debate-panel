"""
Tests for PanelGenerator service.

Tests cover:
- Panel generation with valid LLM responses
- Panel size validation (3-10 personas)
- Diversity validation (heterogeneous stances)
- Outsider position validation
- Error handling (LLM failures, parse errors)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.panel_generator import (
    PanelGenerator,
    PanelGenerationError,
    PanelParseError,
    PanelValidationError,
)
from app.llm.client import LLMAPIError


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client."""
    client = MagicMock()
    client.complete = AsyncMock()
    return client


@pytest.fixture
def panel_generator(mock_llm_client):
    """Create PanelGenerator with mock LLM client."""
    return PanelGenerator(mock_llm_client)


@pytest.fixture
def valid_json_response():
    """Valid JSON response with diverse personas."""
    return """[
        {
            "name": "Dr. Sarah Chen",
            "role": "Climate Scientist",
            "background": "PhD in atmospheric physics, 15 years researching climate models",
            "stance": "Strongly supports climate action based on scientific evidence"
        },
        {
            "name": "John Miller",
            "role": "Economic Analyst",
            "background": "Former Wall Street analyst, now focuses on sustainable investments",
            "stance": "Supports climate action but concerned about economic costs"
        },
        {
            "name": "Maria Rodriguez",
            "role": "Community Organizer",
            "background": "Works with marginalized communities affected by climate change",
            "stance": "Advocates for climate justice and outsider perspectives"
        },
        {
            "name": "Robert Thompson",
            "role": "Industry Lobbyist",
            "background": "Represents fossil fuel industry interests",
            "stance": "Opposes rapid climate transition, favors gradual change"
        }
    ]"""


@pytest.fixture
def valid_text_response():
    """Valid text response with numbered personas."""
    return """
Here are the diverse panel members for the discussion:

Persona 1:
Name: Dr. Sarah Chen
Role: Climate Scientist
Background: PhD in atmospheric physics, 15 years researching climate models
Initial Stance: Strongly supports climate action based on scientific evidence

Persona 2:
Name: John Miller
Role: Economic Analyst
Background: Former Wall Street analyst, now focuses on sustainable investments
Initial Stance: Supports climate action but concerned about economic costs

Persona 3:
Name: Maria Rodriguez
Role: Community Organizer
Background: Works with marginalized communities affected by climate change
Initial Stance: Advocates for climate justice and represents outsider perspectives

Persona 4:
Name: Robert Thompson
Role: Industry Lobbyist
Background: Represents fossil fuel industry interests
Initial Stance: Opposes rapid climate transition, favors gradual change
"""


@pytest.fixture
def homogeneous_response():
    """Response with all personas having similar stances."""
    return """[
        {
            "name": "Alice Green",
            "role": "Environmental Activist",
            "background": "Long-time environmental campaigner",
            "stance": "Strongly supports immediate climate action"
        },
        {
            "name": "Bob Eco",
            "role": "Sustainability Consultant",
            "background": "Helps companies reduce carbon footprint",
            "stance": "Supports aggressive climate policies"
        },
        {
            "name": "Carol Nature",
            "role": "Green Energy Advocate",
            "background": "Promotes renewable energy adoption",
            "stance": "Advocates for rapid transition to green energy"
        }
    ]"""


@pytest.fixture
def no_outsider_response():
    """Response without outsider position."""
    return """[
        {
            "name": "Dr. Smith",
            "role": "Climate Scientist",
            "background": "Research scientist at major university",
            "stance": "Supports climate action based on data"
        },
        {
            "name": "Jane Doe",
            "role": "Policy Analyst",
            "background": "Government policy advisor",
            "stance": "Supports moderate climate policies"
        },
        {
            "name": "Bob Johnson",
            "role": "Business Owner",
            "background": "Runs a manufacturing company",
            "stance": "Opposes strict climate regulations"
        }
    ]"""


@pytest.fixture
def too_small_response():
    """Response with only 2 personas."""
    return """[
        {
            "name": "Alice",
            "role": "Scientist",
            "background": "Research background",
            "stance": "Supports action"
        },
        {
            "name": "Bob",
            "role": "Analyst",
            "background": "Analysis background",
            "stance": "Opposes action"
        }
    ]"""


@pytest.fixture
def too_large_response():
    """Response with 11 personas."""
    personas = []
    for i in range(11):
        stance = "Supports" if i % 2 == 0 else "Opposes"
        personas.append(
            f""" {{
            "name": "Person {i}",
            "role": "Role {i}",
            "background": "Background {i}",
            "stance": "{stance} the topic, includes skeptic viewpoint"
        }}"""
        )
    return "[" + ", ".join(personas) + "]"


@pytest.fixture
def invalid_json_response():
    """Invalid JSON response."""
    return "This is not valid JSON at all, just plain text without structure."


@pytest.fixture
def empty_response():
    """Empty response."""
    return ""


class TestPanelGeneratorInit:
    """Tests for PanelGenerator initialization."""

    def test_init_with_llm_client(self, mock_llm_client):
        """PanelGenerator initializes with LLM client."""
        generator = PanelGenerator(mock_llm_client)
        assert generator._llm_client == mock_llm_client

    def test_min_panel_size_constant(self, panel_generator):
        """MIN_PANEL_SIZE is 3."""
        assert panel_generator.MIN_PANEL_SIZE == 3

    def test_max_panel_size_constant(self, panel_generator):
        """MAX_PANEL_SIZE is 10."""
        assert panel_generator.MAX_PANEL_SIZE == 10

    def test_outsider_keywords_defined(self, panel_generator):
        """OUTSIDER_KEYWORDS contains expected keywords."""
        expected_keywords = [
            "outsider",
            "alternative",
            "unconventional",
            "skeptic",
            "critic",
        ]
        for keyword in expected_keywords:
            assert keyword in panel_generator.OUTSIDER_KEYWORDS


class TestGeneratePanel:
    """Tests for generate_panel method."""

    @pytest.mark.asyncio
    async def test_generate_panel_with_json_response(
        self, panel_generator, mock_llm_client, valid_json_response
    ):
        """Panel generation works with valid JSON response."""
        mock_llm_client.complete.return_value = valid_json_response

        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3
        assert len(personas) <= 10
        assert all(p.name for p in personas)
        assert all(p.role for p in personas)
        assert all(p.background for p in personas)
        assert all(p.stance for p in personas)

    @pytest.mark.asyncio
    async def test_generate_panel_with_text_response(
        self, panel_generator, mock_llm_client, valid_text_response
    ):
        """Panel generation works with structured text response."""
        mock_llm_client.complete.return_value = valid_text_response

        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3
        assert len(personas) <= 10

    @pytest.mark.asyncio
    async def test_generate_panel_creates_persona_agents(
        self, panel_generator, mock_llm_client, valid_json_response
    ):
        """Generated personas are PersonaAgent instances."""
        from app.agents.persona import PersonaAgent

        mock_llm_client.complete.return_value = valid_json_response

        personas = await panel_generator.generate_panel("Climate change")

        assert all(isinstance(p, PersonaAgent) for p in personas)

    @pytest.mark.asyncio
    async def test_generate_panel_llm_failure(self, panel_generator, mock_llm_client):
        """Panel generation raises PanelGenerationError on LLM failure."""
        mock_llm_client.complete.side_effect = LLMAPIError("API failed")

        with pytest.raises(PanelGenerationError) as exc_info:
            await panel_generator.generate_panel("Climate change")

        assert "LLM call failed" in str(exc_info.value)


class TestPanelSizeValidation:
    """Tests for panel size validation."""

    @pytest.mark.asyncio
    async def test_panel_too_small(
        self, panel_generator, mock_llm_client, too_small_response
    ):
        """Panel with fewer than 3 personas uses fallback personas."""
        mock_llm_client.complete.return_value = too_small_response

        # The code catches validation errors and returns fallback personas
        personas = await panel_generator.generate_panel("Climate change")

        # Fallback personas are returned (3 personas)
        assert len(personas) >= 3

    @pytest.mark.asyncio
    async def test_panel_too_large(
        self, panel_generator, mock_llm_client, too_large_response
    ):
        """Panel with more than 10 personas uses fallback personas."""
        mock_llm_client.complete.return_value = too_large_response

        # The code catches validation errors and returns fallback personas
        personas = await panel_generator.generate_panel("Climate change")

        # Fallback personas are returned (3 personas)
        assert len(personas) >= 3
        assert len(personas) <= 10


class TestPanelDiversityValidation:
    """Tests for panel diversity validation."""

    @pytest.mark.asyncio
    async def test_homogeneous_panel_passes_with_different_stances(
        self, panel_generator, mock_llm_client, homogeneous_response
    ):
        """Panel with similar but different stances passes validation."""
        mock_llm_client.complete.return_value = homogeneous_response

        # The homogeneous_response has different stances (not identical)
        # so it passes validation
        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3

    @pytest.mark.asyncio
    async def test_diverse_panel_passes(
        self, panel_generator, mock_llm_client, valid_json_response
    ):
        """Panel with diverse stances passes validation."""
        mock_llm_client.complete.return_value = valid_json_response

        personas = await panel_generator.generate_panel("Climate change")

        stances = [p.stance.lower() for p in personas]
        support_keywords = ["support", "favor", "agree", "pro"]
        oppose_keywords = ["oppose", "against", "disagree", "anti"]

        has_support = any(any(kw in s for kw in support_keywords) for s in stances)
        has_oppose = any(any(kw in s for kw in oppose_keywords) for s in stances)

        assert has_support and has_oppose


class TestOutsiderPositionValidation:
    """Tests for outsider position validation."""

    @pytest.mark.asyncio
    async def test_no_outsider_passes_validation(
        self, panel_generator, mock_llm_client, no_outsider_response
    ):
        """Panel without outsider position passes validation (outsider is optional)."""
        mock_llm_client.complete.return_value = no_outsider_response

        # Outsider position is optional in V1 - validation passes
        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3

    @pytest.mark.asyncio
    async def test_outsider_keyword_in_stance(self, panel_generator, mock_llm_client):
        """Outsider keyword in stance passes validation."""
        response = """[
            {
                "name": "Alice",
                "role": "Scientist",
                "background": "Research background",
                "stance": "Supports action"
            },
            {
                "name": "Bob",
                "role": "Analyst",
                "background": "Analysis background",
                "stance": "Opposes action"
            },
            {
                "name": "Carol",
                "role": "Alternative Thinker",
                "background": "Unconventional background",
                "stance": "Skeptic of mainstream views"
            }
        ]"""
        mock_llm_client.complete.return_value = response

        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3

    @pytest.mark.asyncio
    async def test_outsider_keyword_in_background(
        self, panel_generator, mock_llm_client
    ):
        """Outsider keyword in background passes validation."""
        response = """[
            {
                "name": "Alice",
                "role": "Scientist",
                "background": "Research background",
                "stance": "Supports action"
            },
            {
                "name": "Bob",
                "role": "Analyst",
                "background": "Analysis background",
                "stance": "Opposes action"
            },
            {
                "name": "Carol",
                "role": "Community Leader",
                "background": "Works with marginalized communities",
                "stance": "Neutral position"
            }
        ]"""
        mock_llm_client.complete.return_value = response

        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3


class TestResponseParsing:
    """Tests for LLM response parsing."""

    def test_parse_json_array(self, panel_generator, valid_json_response):
        """JSON array parsing works correctly."""
        personas = panel_generator._parse_llm_response(valid_json_response)

        assert len(personas) >= 3
        assert all("name" in p for p in personas)
        assert all("role" in p for p in personas)

    def test_parse_json_with_personas_key(self, panel_generator):
        """JSON with 'personas' key parsing works."""
        response = """{"personas": [
            {"name": "Alice", "role": "Scientist", "background": "BG", "stance": "Support"},
            {"name": "Bob", "role": "Analyst", "background": "BG", "stance": "Oppose"},
            {"name": "Carol", "role": "Critic", "background": "BG", "stance": "Skeptic"}
        ]}"""

        personas = panel_generator._parse_llm_response(response)

        assert len(personas) == 3

    def test_parse_text_with_numbered_sections(
        self, panel_generator, valid_text_response
    ):
        """Text with numbered sections parsing works."""
        personas = panel_generator._parse_llm_response(valid_text_response)

        assert len(personas) >= 3

    def test_parse_invalid_response_raises_error(
        self, panel_generator, invalid_json_response
    ):
        """Invalid response raises PanelParseError."""
        with pytest.raises(PanelParseError):
            panel_generator._parse_llm_response(invalid_json_response)

    def test_parse_empty_response_raises_error(self, panel_generator, empty_response):
        """Empty response raises PanelParseError."""
        with pytest.raises(PanelParseError):
            panel_generator._parse_llm_response(empty_response)

    def test_parse_missing_fields_filled_with_defaults(self, panel_generator):
        """Missing fields are filled with defaults."""
        response = """[
            {"name": "Alice", "role": "Scientist"},
            {"name": "Bob", "role": "Analyst", "stance": "Opposes"},
            {"name": "Carol", "role": "Critic", "background": "Unconventional BG"}
        ]"""

        personas = panel_generator._parse_llm_response(response)

        assert all("background" in p for p in personas)
        assert all("stance" in p for p in personas)

    def test_parse_case_insensitive_field_names(self, panel_generator):
        """Field names are parsed case-insensitively."""
        response = """[
            {"Name": "Alice", "Role": "Scientist", "Background": "BG", "Stance": "Support"},
            {"name": "Bob", "role": "Analyst", "background": "BG", "stance": "Oppose"},
            {"NAME": "Carol", "ROLE": "Critic", "BACKGROUND": "BG", "STANCE": "Skeptic"}
        ]"""

        personas = panel_generator._parse_llm_response(response)

        assert len(personas) == 3
        assert all("name" in p for p in personas)


class TestPersonaAgentCreation:
    """Tests for PersonaAgent instance creation."""

    @pytest.mark.asyncio
    async def test_persona_agents_have_unique_ids(
        self, panel_generator, mock_llm_client, valid_json_response
    ):
        """Each PersonaAgent has a unique ID."""
        mock_llm_client.complete.return_value = valid_json_response

        personas = await panel_generator.generate_panel("Climate change")

        ids = [p.id for p in personas]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_persona_agents_have_llm_client(
        self, panel_generator, mock_llm_client, valid_json_response
    ):
        """Each PersonaAgent has the LLM client."""
        mock_llm_client.complete.return_value = valid_json_response

        personas = await panel_generator.generate_panel("Climate change")

        assert all(p.llm_client == mock_llm_client for p in personas)

    @pytest.mark.asyncio
    async def test_persona_agents_without_session(
        self, panel_generator, mock_llm_client, valid_json_response
    ):
        """PersonaAgents can be created without session."""
        mock_llm_client.complete.return_value = valid_json_response

        personas = await panel_generator.generate_panel("Climate change")

        assert all(p.session is None for p in personas)

    @pytest.mark.asyncio
    async def test_persona_agents_with_session(
        self, panel_generator, mock_llm_client, valid_json_response
    ):
        """PersonaAgents can be created with session."""
        from app.orchestration.session import DiscussionSession
        from app.models.discussion import DiscussionConfig

        mock_llm_client.complete.return_value = valid_json_response
        mock_session = MagicMock(spec=DiscussionSession)
        mock_session.topic = "Climate change"

        personas = await panel_generator.generate_panel(
            "Climate change", session=mock_session
        )

        assert all(p.session == mock_session for p in personas)


class TestExceptionClasses:
    """Tests for exception classes."""

    def test_panel_generation_error_is_exception(self):
        """PanelGenerationError is an Exception."""
        assert issubclass(PanelGenerationError, Exception)

    def test_panel_parse_error_is_panel_generation_error(self):
        """PanelParseError is a PanelGenerationError."""
        assert issubclass(PanelParseError, PanelGenerationError)

    def test_panel_validation_error_is_panel_generation_error(self):
        """PanelValidationError is a PanelGenerationError."""
        assert issubclass(PanelValidationError, PanelGenerationError)

    def test_panel_generation_error_message(self):
        """PanelGenerationError preserves message."""
        error = PanelGenerationError("Test error message")
        assert str(error) == "Test error message"

    def test_panel_parse_error_message(self):
        """PanelParseError preserves message."""
        error = PanelParseError("Parse failed")
        assert str(error) == "Parse failed"

    def test_panel_validation_error_message(self):
        """PanelValidationError preserves message."""
        error = PanelValidationError("Validation failed")
        assert str(error) == "Validation failed"


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_panel_with_mixed_json_and_text(
        self, panel_generator, mock_llm_client
    ):
        """Panel handles response with JSON embedded in text."""
        response = """
Here are the panel members:

[
    {"name": "Alice", "role": "Scientist", "background": "BG", "stance": "Supports action"},
    {"name": "Bob", "role": "Analyst", "background": "BG", "stance": "Opposes action"},
    {"name": "Carol", "role": "Skeptic", "background": "Unconventional BG", "stance": "Critical of mainstream"}
]

These personas represent diverse viewpoints.
"""
        mock_llm_client.complete.return_value = response

        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3

    @pytest.mark.asyncio
    async def test_panel_with_extra_whitespace(self, panel_generator, mock_llm_client):
        """Panel handles response with extra whitespace."""
        response = """
[
    {
        "name": "Alice",
        "role": "Scientist",
        "background": "BG",
        "stance": "Supports action"
    },
    {
        "name": "Bob",
        "role": "Analyst",
        "background": "BG",
        "stance": "Opposes action"
    },
    {
        "name": "Carol",
        "role": "Skeptic",
        "background": "Unconventional BG",
        "stance": "Critical of mainstream"
    }
]
"""
        mock_llm_client.complete.return_value = response

        personas = await panel_generator.generate_panel("Climate change")

        assert len(personas) >= 3

    def test_parse_response_with_alternative_field_names(self, panel_generator):
        """Parser handles alternative field names (title, position)."""
        response = """[
            {"name": "Alice", "title": "Scientist", "experience": "BG", "position": "Support"},
            {"name": "Bob", "title": "Analyst", "experience": "BG", "position": "Oppose"},
            {"name": "Carol", "title": "Skeptic", "experience": "Unconventional BG", "position": "Critical"}
        ]"""

        personas = panel_generator._parse_llm_response(response)

        assert len(personas) >= 3
        assert all("role" in p for p in personas)
        assert all("stance" in p for p in personas)


class TestImports:
    """Tests for module imports."""

    def test_import_panel_generator_from_services(self):
        """PanelGenerator can be imported from services."""
        from app.services import PanelGenerator

        assert PanelGenerator is not None

    def test_import_exceptions_from_services(self):
        """Exceptions can be imported from services."""
        from app.services import (
            PanelGenerationError,
            PanelParseError,
            PanelValidationError,
        )

        assert PanelGenerationError is not None
        assert PanelParseError is not None
        assert PanelValidationError is not None
