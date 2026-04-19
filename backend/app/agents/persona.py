"""
PersonaAgent - Generates responses for discussion panel members.

Each persona has a unique identity, background, and stance that can
adapt during the discussion based on arguments presented.
"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from app.agents.base import BaseAgent
from app.llm.client import LLMClient
from app.llm.prompts import PERSONA_PROMPT, PERSONA_INTRODUCTION_PROMPT
from app.models.agent import AgentType
from app.models.message import Message, MessageType
from app.orchestration.event_bus import AgentMessageEvent
from app.utils.language import detect_language
from app.utils.emoji_map import infer_emoji

if TYPE_CHECKING:
    from app.orchestration.session import DiscussionSession
    from app.models.agent import Agent


class PersonaAgent(BaseAgent):
    """
    Agent representing a discussion panel member with a unique persona.

    Each persona has:
    - A role/title (e.g., "Climate Scientist", "Policy Analyst")
    - A background (professional experience, expertise)
    - A stance on the topic (can adapt during discussion)

    The persona generates responses using the LLM, staying in character
    and potentially changing stance based on compelling arguments.
    """

    def __init__(
        self,
        id: str,
        name: str,
        role: str,
        background: str,
        stance: str,
        llm_client: LLMClient,
        session: Optional["DiscussionSession"] = None,
        emoji: str = "",
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            type=AgentType.PERSONA,
            llm_client=llm_client,
            session=session,
        )
        self.role = role
        self.background = background
        self._stance = stance
        self.emoji = emoji or infer_emoji(role)

    @property
    def stance(self) -> str:
        return self._stance

    @stance.setter
    def stance(self, value: str) -> None:
        self._stance = value

    def update_stance(self, new_stance: str) -> None:
        """
        Update the persona's stance on the topic.

        Stance can change during discussion if compelling arguments
        are presented. This is tracked for synthesis/summary.

        Args:
            new_stance: The new stance position
        """
        self._stance = new_stance

    async def introduce(self) -> Message:
        topic = self.session.topic if self.session else "Unknown topic"
        language = detect_language(topic)

        system_prompt = PERSONA_INTRODUCTION_PROMPT(
            name=self.name,
            role=self.role,
            background=self.background,
            stance=self._stance,
            topic=topic,
            language=language,
            consensus_mode=self.session.config.consensus_mode
            if self.session
            else False,
        )

        messages = [{"role": "user", "content": system_prompt}]

        try:
            full_content = await asyncio.wait_for(
                self._stream_llm(messages),
                timeout=60,
            )
        except asyncio.TimeoutError:
            if self.session:
                self.session.logger.log_error(
                    "persona", f"Introduction timeout for {self.name}"
                )
            full_content = f"Hallo, ich bin {self.name}. {self.role}. {self._stance}"

        message = self._create_message(full_content, MessageType.AGENT)

        if self.session:
            from app.orchestration.event_bus import AgentMessageEvent
            from app.models.agent import AgentType

            event = AgentMessageEvent(
                agent_id=self.id,
                agent_type=AgentType.PERSONA.value,
                content=full_content,
                metadata={
                    "message_id": message.id,
                    "timestamp": message.timestamp.isoformat(),
                    "persona_name": self.name,
                    "persona_role": self.role,
                    "is_introduction": True,
                },
            )
            self.session.event_bus.publish(event)

        return message

    async def generate_response(self, context: list[dict]) -> Message:
        """
        Generate a response based on the conversation context.

        Uses PERSONA_PROMPT to format the system prompt with persona
        attributes, then calls the LLM to generate a response.

        Args:
            context: List of message dictionaries with 'role' and 'content'

        Returns:
            Message object containing the persona's response

        Raises:
            LLMAPIError: If LLM call fails after retries
        """
        topic = self.session.topic if self.session else "Unknown topic"
        language = detect_language(topic)

        system_prompt = PERSONA_PROMPT(
            name=self.name,
            role=self.role,
            background=self.background,
            stance=self._stance,
            topic=topic,
            language=language,
            consensus_mode=self.session.config.consensus_mode
            if self.session
            else False,
        )

        formatted_messages = self._format_messages_for_llm(context, system_prompt)

        try:
            full_content = await asyncio.wait_for(
                self._stream_llm(formatted_messages),
                timeout=60,
            )
        except asyncio.TimeoutError:
            if self.session:
                self.session.logger.log_error(
                    "persona", f"LLM timeout for {self.name} after 60s"
                )
            full_content = ""

        if not full_content or len(full_content.strip()) < 10:
            full_content = f"I have to say honestly, after what was said here, I'm reconsidering. {self.name} here - I'm sticking with my position, but I'm listening to you."

        message = self._create_message(full_content, MessageType.AGENT)

        if self.session:
            event = AgentMessageEvent(
                agent_id=self.id,
                agent_type=AgentType.PERSONA.value,
                content=full_content,
                metadata={
                    "message_id": message.id,
                    "timestamp": message.timestamp.isoformat(),
                    "persona_name": self.name,
                    "persona_role": self.role,
                    "current_stance": self._stance,
                },
            )
            self.session.event_bus.publish(event)

        return message

    def to_agent_model(self) -> "Agent":
        from app.models.agent import Agent

        return Agent(
            id=self.id,
            name=self.name,
            role=self.role,
            background=self.background,
            stance=self._stance,
            type=self.type,
            emoji=self.emoji,
        )
