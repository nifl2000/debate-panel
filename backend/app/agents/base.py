"""
Base Agent Abstract Class

Provides the foundation for all agent types in the debate panel system.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.models.agent import AgentType
from app.models.discussion import DiscussionSession
from app.models.message import Message, MessageType
from app.llm.client import LLMClient
from app.utils.token_counter import count_tokens


class BaseAgent(ABC):
    """
    Abstract base class for all agent types.

    Provides shared functionality for context windowing, message formatting,
    and LLM interaction. Subclasses must implement generate_response.
    """

    def __init__(
        self,
        id: str,
        name: str,
        type: AgentType,
        llm_client: LLMClient,
        session: Optional[DiscussionSession] = None,
    ) -> None:
        """
        Initialize the base agent.

        Args:
            id: Unique identifier for the agent
            name: Display name of the agent
            type: Type of agent (PERSONA, MODERATOR, FACT_CHECKER)
            llm_client: LLM client instance for generating responses
            session: Optional discussion session for context access
        """
        self.id = id
        self.name = name
        self.type = type
        self.llm_client = llm_client
        self.session = session

    @abstractmethod
    async def generate_response(self, context: list[dict]) -> Message:
        """
        Generate a response based on the conversation context.

        Args:
            context: List of message dictionaries with 'role' and 'content'

        Returns:
            Message object containing the agent's response
        """
        pass

    def _get_context_window(
        self, messages: list[dict], max_tokens: int = 8000
    ) -> list[dict]:
        """
        Window conversation history to fit within token limit.

        Takes messages from the end of the conversation, keeping the most recent
        messages that fit within the token limit.

        Args:
            messages: List of message dictionaries
            max_tokens: Maximum tokens to include (default: 8000)

        Returns:
            Filtered list of messages that fit within token limit
        """
        if not messages:
            return []

        if count_tokens(messages) <= max_tokens:
            return messages

        windowed_messages = []
        for message in reversed(messages):
            test_messages = [message] + windowed_messages
            if count_tokens(test_messages) <= max_tokens:
                windowed_messages = [message] + windowed_messages
            else:
                break

        return windowed_messages

    def _format_messages_for_llm(
        self, context: list[dict], system_prompt: str
    ) -> list[dict]:
        """
        Format messages for LLM consumption with system prompt.

        Args:
            context: List of message dictionaries
            system_prompt: System prompt to prepend

        Returns:
            Formatted list of messages with system prompt
        """
        formatted = [{"role": "system", "content": system_prompt}]
        formatted.extend(context)
        return formatted

    async def _stream_llm(self, messages: list[dict]) -> str:
        chunks: list[str] = []
        async for chunk in self.llm_client.stream_chat(messages):
            chunks.append(chunk)
        return "".join(chunks).strip()

    def _create_message(self, content: str, message_type: MessageType) -> Message:
        return Message(
            id=f"msg_{uuid.uuid4().hex[:8]}",
            agent_id=self.id,
            content=content,
            timestamp=datetime.now(),
            type=message_type,
        )
