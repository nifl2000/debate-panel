"""Unit tests for prompt templates."""

import pytest
from app.llm.prompts import (
    PERSONA_PROMPT,
    MODERATOR_PROMPT,
    FACT_CHECK_PROMPT,
    PANEL_GENERATION_PROMPT,
    SYNTHESIS_PROMPT,
)


class TestPersonaPrompt:
    def test_returns_non_empty_string(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_name(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "Alice" in result

    def test_includes_role(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "Scientist" in result

    def test_includes_background(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "Climate researcher" in result

    def test_includes_stance(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "Supports action" in result

    def test_includes_topic(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "Climate change" in result

    def test_contains_stay_in_character_instruction(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "Stay in character" in result

    def test_contains_engage_instruction(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "respond" in result.lower() or "perspective" in result.lower()

    def test_contains_change_stance_instruction(self):
        result = PERSONA_PROMPT(
            name="Alice",
            role="Scientist",
            background="Climate researcher",
            stance="Supports action",
            topic="Climate change",
            language="German",
        )
        assert "change your stance" in result


class TestModeratorPrompt:
    def test_returns_non_empty_string(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_topic(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert "Climate change" in result

    def test_includes_panel_size(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert "5" in result

    def test_includes_max_messages(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert "20" in result

    def test_contains_control_flow_instruction(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert "Control flow" in result or "flow" in result.lower()

    def test_contains_detect_stalls_instruction(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert "Detect stalling" in result

    def test_contains_integrate_fact_checks_instruction(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert "Integrate fact-checks" in result

    def test_contains_select_speaker_instruction(self):
        result = MODERATOR_PROMPT(topic="Climate change", panel_size=5, max_messages=20, language="German")
        assert "Select next speaker" in result or "speaker" in result.lower()


class TestFactCheckPrompt:
    def test_returns_non_empty_string(self):
        result = FACT_CHECK_PROMPT(
            claim="The earth is round", context="Discussion about planetary science"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_claim(self):
        result = FACT_CHECK_PROMPT(
            claim="The earth is round", context="Discussion about planetary science"
        )
        assert "The earth is round" in result

    def test_includes_context(self):
        result = FACT_CHECK_PROMPT(
            claim="The earth is round", context="Discussion about planetary science"
        )
        assert "Discussion about planetary science" in result

    def test_contains_verify_instruction(self):
        result = FACT_CHECK_PROMPT(
            claim="The earth is round", context="Discussion about planetary science"
        )
        assert "Verify the factual accuracy" in result

    def test_contains_evaluate_sources_instruction(self):
        result = FACT_CHECK_PROMPT(
            claim="The earth is round", context="Discussion about planetary science"
        )
        assert "source" in result.lower() or "evidence" in result.lower()

    def test_contains_verdict_instruction(self):
        result = FACT_CHECK_PROMPT(
            claim="The earth is round", context="Discussion about planetary science"
        )
        assert "verdict" in result.lower()


class TestPanelGenerationPrompt:
    def test_returns_non_empty_string(self):
        result = PANEL_GENERATION_PROMPT(topic="Climate change")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_topic(self):
        result = PANEL_GENERATION_PROMPT(topic="Climate change")
        assert "Climate change" in result

    def test_contains_diversity_instruction(self):
        result = PANEL_GENERATION_PROMPT(topic="Climate change")
        assert (
            "divers" in result.lower()
            or "different" in result.lower()
            or "mix" in result.lower()
        )

    def test_contains_outsider_instruction(self):
        result = PANEL_GENERATION_PROMPT(topic="Climate change")
        assert (
            "MECE" in result
            or "distinct" in result.lower()
            or "different" in result.lower()
        )

    def test_contains_heterogeneous_instruction(self):
        result = PANEL_GENERATION_PROMPT(topic="Climate change")
        assert (
            "MECE" in result
            or "different" in result.lower()
            or "distinct" in result.lower()
        )


class TestSynthesisPrompt:
    def test_returns_non_empty_string(self):
        result = SYNTHESIS_PROMPT(
            topic="Climate change",
            conversation="Person A: I think... Person B: I disagree...",
            language="German",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_topic(self):
        result = SYNTHESIS_PROMPT(
            topic="Climate change",
            conversation="Person A: I think... Person B: I disagree...",
            language="German",
        )
        assert "Climate change" in result

    def test_includes_conversation(self):
        result = SYNTHESIS_PROMPT(
            topic="Climate change",
            conversation="Person A: I think climate change is real.",
            language="German",
        )
        assert "Person A: I think climate change is real." in result

    def test_contains_summarize_instruction(self):
        result = SYNTHESIS_PROMPT(
            topic="Climate change",
            conversation="Person A: I think... Person B: I disagree...",
            language="German",
        )
        assert "Summary" in result or "summar" in result.lower()

    def test_contains_agreement_instruction(self):
        result = SYNTHESIS_PROMPT(
            topic="Climate change",
            conversation="Person A: I think... Person B: I disagree...",
            language="German",
        )
        assert (
            "Common" in result
            or "agreement" in result.lower()
            or "insights" in result.lower()
        )

    def test_contains_disagreement_instruction(self):
        result = SYNTHESIS_PROMPT(
            topic="Climate change",
            conversation="Person A: I think... Person B: I disagree...",
            language="German",
        )
        assert (
            "Controversies" in result
            or "disagreement" in result.lower()
            or "open questions" in result.lower()
        )
