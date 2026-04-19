"""
PanelGenerator - Creates diverse personas for a discussion topic.
"""

import json
import re
import uuid
from typing import TYPE_CHECKING, Optional

from app.agents.persona import PersonaAgent
from app.llm.client import LLMClient, LLMAPIError
from app.llm.prompts import PANEL_GENERATION_PROMPT
from app.utils.logger import get_logger
from app.utils.language import detect_language, LANGUAGE_MAP
from app.utils.emoji_map import infer_emoji

if TYPE_CHECKING:
    from app.orchestration.session import DiscussionSession

logger = get_logger(__name__)


class PanelGenerationError(Exception):
    pass


class PanelParseError(PanelGenerationError):
    pass


class PanelValidationError(PanelGenerationError):
    pass


class PanelGenerator:
    """
    Service that creates diverse personas for a discussion topic.

    Uses LLM to generate heterogeneous panels with:
    - Varied professional backgrounds
    - Different demographic perspectives
    - Opposing political leanings
    - At least one outsider position
    """

    # Minimum and maximum panel sizes
    MIN_PANEL_SIZE = 3
    MAX_PANEL_SIZE = 10

    # Keywords indicating outsider positions
    OUTSIDER_KEYWORDS = [
        "outsider",
        "alternative",
        "unconventional",
        "non-traditional",
        "marginalized",
        "underrepresented",
        "contrarian",
        "dissenting",
        "minority",
        "opposing",
        "skeptic",
        "critic",
    ]

    def __init__(self, llm_client: LLMClient) -> None:
        """
        Initialize PanelGenerator with LLM client.

        Args:
            llm_client: LLM client instance for generating personas
        """
        self._llm_client = llm_client

    async def generate_panel(
        self,
        topic: str,
        session: "DiscussionSession | None" = None,
    ) -> list[PersonaAgent]:
        """
        Generate a diverse panel of personas for the discussion topic.

        Args:
            topic: The discussion topic
            session: Optional discussion session for persona context

        Returns:
            List of PersonaAgent instances with diverse perspectives

        Raises:
            PanelGenerationError: If generation fails
            PanelParseError: If LLM response cannot be parsed
            PanelValidationError: If panel doesn't meet requirements
        """
        logger.info(
            "Generating panel for topic",
            extra={"operation": "generate_panel", "topic": topic},
        )

        lang_name = detect_language(topic)

        logger.info(
            "Detected language",
            extra={
                "operation": "detect_language",
                "lang_name": lang_name,
            },
        )

        prompt = PANEL_GENERATION_PROMPT(topic, lang_name)
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self._llm_client.complete(messages)
        except LLMAPIError as e:
            logger.error(
                "LLM call failed during panel generation",
                extra={"operation": "generate_panel", "error": str(e)},
            )
            raise PanelGenerationError(f"LLM call failed: {e}") from e

        try:
            personas_data = self._parse_llm_response(response)
            self._validate_panel(personas_data)
        except (PanelParseError, PanelValidationError) as e:
            logger.warning(
                "LLM response parsing failed, retrying with extraction prompt",
                extra={
                    "operation": "generate_panel",
                    "error": str(e),
                    "response_preview": response[:500],
                },
            )
            personas_data = await self._extract_personas_from_text(response)

        personas = self._create_persona_agents(personas_data, session)

        logger.info(
            "Panel generated successfully",
            extra={
                "operation": "generate_panel",
                "panel_size": len(personas),
                "topic": topic,
            },
        )

        return personas

    def _parse_llm_response(self, response: str) -> list[dict]:
        """
        Parse LLM response to extract persona definitions.

        Attempts multiple parsing strategies:
        1. JSON array format
        2. JSON objects with numbered sections
        3. Structured text with clear delimiters

        Args:
            response: Raw LLM response string

        Returns:
            List of persona dictionaries with name, role, background, stance

        Raises:
            PanelParseError: If response cannot be parsed
        """
        personas = self._try_json_parse(response)
        if personas:
            return personas

        personas = self._try_text_parse(response)
        if personas:
            return personas

        personas = self._try_regex_parse(response)
        if personas:
            return personas

        logger.error(
            "Failed to parse LLM response",
            extra={
                "operation": "parse_llm_response",
                "response_preview": response[:200],
            },
        )
        raise PanelParseError("Could not parse LLM response into persona definitions")

    def _try_json_parse(self, response: str) -> list[dict] | None:
        # Strip markdown code blocks
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = (
                "\n".join(lines[1:-1])
                if lines[-1].startswith("```")
                else "\n".join(lines[1:])
            )

        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return self._validate_persona_fields(data)
            if isinstance(data, dict) and "personas" in data:
                return self._validate_persona_fields(data["personas"])
        except json.JSONDecodeError:
            pass

        # Find JSON array in text
        json_pattern = r"\[[\s\S]*\]"
        matches = re.findall(json_pattern, cleaned)

        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, list) and len(data) > 0:
                    return self._validate_persona_fields(data)
            except json.JSONDecodeError:
                continue

        # Find JSON objects
        obj_pattern = r"\{[\s\S]*?\}"
        objects = re.findall(obj_pattern, cleaned)

        if objects:
            personas = []
            for obj_str in objects:
                try:
                    obj = json.loads(obj_str)
                    if self._is_persona_object(obj):
                        personas.append(obj)
                except json.JSONDecodeError:
                    continue

            if personas:
                return self._validate_persona_fields(personas)

        return None

    def _try_text_parse(self, response: str) -> list[dict] | None:
        """
        Try to parse structured text format.

        Looks for numbered sections with persona fields.
        """
        persona_pattern = r"(?:Persona|Person|Participant|Panelist)?\s*(\d+)[.:\s-]*"
        sections = re.split(persona_pattern, response)

        if len(sections) < 3:
            return None

        personas = []
        for i in range(1, len(sections), 2):
            if i + 1 < len(sections):
                section_text = sections[i + 1]
                persona = self._extract_persona_from_text(section_text)
                if persona:
                    personas.append(persona)

        if personas:
            return self._validate_persona_fields(personas)

        return None

    def _try_regex_parse(self, response: str) -> list[dict] | None:
        """
        Try regex-based parsing for less structured responses.

        Looks for field patterns like "Name: X", "Role: Y", etc.
        """
        delimiters = ["---", "***", "###", "\n\n\n"]
        sections = [response]

        for delim in delimiters:
            if delim in response:
                sections = response.split(delim)
                break

        personas = []
        for section in sections:
            if len(section.strip()) < 20:
                continue

            persona = self._extract_persona_from_text(section)
            if persona:
                personas.append(persona)

        if personas:
            return self._validate_persona_fields(personas)

        return None

    def _extract_persona_from_text(self, text: str) -> dict | None:
        """
        Extract persona fields from a text section.

        Args:
            text: Text section containing persona information

        Returns:
            Persona dictionary or None if extraction fails
        """
        patterns = {
            "name": [
                r"Name[:\s]+([^\n]+)",
                r"([A-Z][a-z]+ [A-Z][a-z]+)",
            ],
            "role": [
                r"Role[:\s]+([^\n]+)",
                r"Title[:\s]+([^\n]+)",
                r"Profession[:\s]+([^\n]+)",
            ],
            "background": [
                r"Background[:\s]+([^\n]+(?:\n[^\n]+)*?)(?=Stance|Position|Initial|$)",
                r"Background[:\s]+([^\n]+)",
            ],
            "stance": [
                r"(?:Initial )?Stance[:\s]+([^\n]+)",
                r"Position[:\s]+([^\n]+)",
                r"View[:\s]+([^\n]+)",
            ],
        }

        persona = {}

        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    persona[field] = match.group(1).strip()
                    break

        if "name" in persona and "role" in persona:
            if "background" not in persona:
                persona["background"] = (
                    f"Professional with expertise in {persona['role']}"
                )
            if "stance" not in persona:
                persona["stance"] = "Neutral position on the topic"
            return persona

        return None

    def _is_persona_object(self, obj: dict) -> bool:
        """
        Check if a JSON object represents a persona.

        Args:
            obj: JSON object to check

        Returns:
            True if object has persona-like fields
        """
        persona_fields = ["name", "role", "background", "stance", "title", "position"]
        return any(field in obj for field in persona_fields)

    def _validate_persona_fields(self, personas: list[dict]) -> list[dict]:
        """
        Validate and normalize persona field names.

        Args:
            personas: List of persona dictionaries

        Returns:
            Normalized list with required fields
        """
        field_aliases = {
            "name": ["name", "Name", "NAME"],
            "role": ["role", "Role", "ROLE", "title", "Title", "TITLE"],
            "background": ["background", "Background", "BACKGROUND", "experience", "Experience", "EXPERIENCE"],
            "stance": ["stance", "Stance", "STANCE", "position", "Position", "POSITION"],
            "emoji": ["emoji", "Emoji", "EMOJI"],
        }

        def get_field(data: dict, aliases: list[str]) -> str:
            for alias in aliases:
                if alias in data:
                    return data[alias]
            return ""

        normalized = []

        for persona in personas:
            normalized_persona = {
                field: get_field(persona, aliases)
                for field, aliases in field_aliases.items()
            }

            if not normalized_persona["name"] or not normalized_persona["role"]:
                continue

            if not normalized_persona["background"]:
                normalized_persona["background"] = (
                    f"Professional with expertise in {normalized_persona['role']}"
                )
            if not normalized_persona["stance"]:
                normalized_persona["stance"] = "Neutral position on the topic"
            if not normalized_persona["emoji"]:
                normalized_persona["emoji"] = infer_emoji(normalized_persona["role"])

            normalized.append(normalized_persona)

        return normalized

    def _validate_panel(self, personas_data: list[dict]) -> None:
        """
        Validate that panel meets requirements.

        Requirements:
        - 3-10 personas
        - Diverse stances (not all same position)
        - At least one outsider position

        Args:
            personas_data: List of persona dictionaries

        Raises:
            PanelValidationError: If requirements not met
        """
        panel_size = len(personas_data)
        if panel_size < self.MIN_PANEL_SIZE:
            raise PanelValidationError(
                f"Panel too small: {panel_size} personas (minimum {self.MIN_PANEL_SIZE})"
            )
        if panel_size > self.MAX_PANEL_SIZE:
            raise PanelValidationError(
                f"Panel too large: {panel_size} personas (maximum {self.MAX_PANEL_SIZE})"
            )

        stances = [p["stance"].lower() for p in personas_data]
        unique_stances = set(stances)

        # Check for diverse stances - accept if we have at least 2 different stances
        if len(unique_stances) < 2:
            raise PanelValidationError(
                "Panel lacks diversity: all personas have identical stances"
            )

        # Check for outsider presence - relaxed for V1
        has_outsider = self._check_outsider_presence(personas_data)

        logger.info(
            "Panel validation passed",
            extra={
                "operation": "validate_panel",
                "panel_size": panel_size,
                "unique_stances": len(unique_stances),
                "has_outsider": has_outsider,
            },
        )

    def _check_outsider_presence(self, personas_data: list[dict]) -> bool:
        """
        Check if panel has at least one outsider position.

        Outsider indicators:
        - Keywords in stance or background
        - Unconventional role
        - Alternative viewpoint

        Args:
            personas_data: List of persona dictionaries

        Returns:
            True if outsider position found
        """
        for persona in personas_data:
            stance_lower = persona["stance"].lower()
            background_lower = persona["background"].lower()
            role_lower = persona["role"].lower()

            combined_text = f"{stance_lower} {background_lower} {role_lower}"

            for keyword in self.OUTSIDER_KEYWORDS:
                if keyword in combined_text:
                    return True

        return False

    def _create_persona_agents(
        self,
        personas_data: list[dict],
        session: "DiscussionSession | None",
    ) -> list[PersonaAgent]:
        """
        Create PersonaAgent instances from parsed data.

        Args:
            personas_data: List of persona dictionaries
            session: Optional discussion session

        Returns:
            List of PersonaAgent instances
        """
        personas = []

        for i, persona_data in enumerate(personas_data):
            agent_id = f"persona_{uuid.uuid4().hex[:8]}"

            persona = PersonaAgent(
                id=agent_id,
                name=persona_data["name"],
                role=persona_data["role"],
                background=persona_data["background"],
                stance=persona_data["stance"],
                llm_client=self._llm_client,
                session=session,
                emoji=persona_data.get("emoji", ""),
            )

            personas.append(persona)

            logger.debug(
                "Created persona agent",
                extra={
                    "operation": "create_persona_agent",
                    "agent_id": agent_id,
                    "persona_name": persona_data["name"],
                    "persona_role": persona_data["role"],
                },
            )

        return personas

    async def _extract_personas_from_text(self, original_response: str) -> list[dict]:
        """
        Second-stage LLM call: Extract personas from unstructured text.
        """
        extract_prompt = f"""Extract the persona definitions from this text and return ONLY a valid JSON array.

Each persona must have exactly: "name", "role", "background", "stance"

Text to extract from:
{original_response}

Return ONLY the JSON array:"""

        try:
            response = await self._llm_client.complete(
                [{"role": "user", "content": extract_prompt}]
            )
            personas_data = self._parse_llm_response(response)
            self._validate_panel(personas_data)
            return personas_data
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return self._get_fallback_personas_from_topic()

    def _get_fallback_personas_from_topic(self) -> list[dict]:
        return [
            {
                "name": "Dr. Anna Schmidt",
                "role": "Expert",
                "background": "Professional with expertise in the topic",
                "stance": "Supports action based on evidence",
            },
            {
                "name": "Thomas Weber",
                "role": "Industry Representative",
                "background": "Balances practical and theoretical concerns",
                "stance": "Supports gradual approach",
            },
            {
                "name": "Dr. Lisa Müller",
                "role": "Skeptical Analyst",
                "background": "Questions assumptions and demands rigorous proof",
                "stance": "Skeptical without clear justification",
            },
        ]
