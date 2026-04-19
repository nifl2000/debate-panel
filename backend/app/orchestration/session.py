"""
DiscussionSession class for managing discussion state and orchestration.

This is the runtime class that manages discussion state, not the Pydantic model.
The Pydantic model (app.models.discussion.DiscussionSession) is for data representation.
"""

import asyncio
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app.models.discussion import DiscussionConfig, DiscussionState
from app.models.message import Message, MessageType
from app.orchestration.event_bus import AgentMessageEvent, EventBus
from app.agents.base import BaseAgent
from app.utils.token_counter import count_tokens, DEFAULT_TOKEN_LIMIT

if TYPE_CHECKING:
    from app.models.discussion import DiscussionSession as PydanticDiscussionSession


class DiscussionSession:
    """
    Runtime class for managing discussion state and orchestration.

    Provides:
    - Thread-safe conversation log management (asyncio.Lock)
    - Event publishing on message addition
    - Context windowing for agents
    - Lifecycle management (start, pause, stop, cleanup)
    """

    def __init__(
        self,
        topic: str,
        event_bus: EventBus,
        config: Optional[DiscussionConfig] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """
        Initialize a discussion session.

        Args:
            topic: The topic or question being discussed
            event_bus: Event bus instance for publishing events
            config: Discussion configuration (defaults to DiscussionConfig())
            session_id: Optional session ID (defaults to UUID)
        """
        self.id: str = session_id or str(uuid.uuid4())
        self.topic: str = topic
        self.state: DiscussionState = DiscussionState.PAUSED
        self.phase: str = "INTRODUCTION"  # INTRODUCTION, DISCUSSION, COMPLETED
        self.event_bus: EventBus = event_bus
        self.agents: Dict[str, BaseAgent] = {}
        self.conversation_log: List[Message] = []
        self.config: DiscussionConfig = config or DiscussionConfig()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._created_at: datetime = datetime.now()
        self._last_activity: datetime = datetime.now()
        self._marked_for_cleanup: bool = False

        self._speaker_history: List[str] = []
        self._message_count: int = 0
        self._introduction_done: bool = False
        self._paused: bool = False
        self._stop_requested: bool = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._inject_queue: asyncio.Queue = asyncio.Queue()

        from app.services.session_logger import SessionLogger

        self.logger = SessionLogger(self.id, self.topic)
        self.logger.log(
            "session",
            "created",
            {"topic": topic, "max_messages": self.config.max_messages},
        )

        self._session_writer: Any = None

        self._generation_status: str = "starting"
        self._generation_message: str = "Starting discussion..."
        self._generation_task: Any = None
        self._personas: list = []
        self._moderator_name: str = ""

    @property
    def generation_status(self) -> str:
        return self._generation_status

    @generation_status.setter
    def generation_status(self, value: str) -> None:
        self._generation_status = value

    @property
    def generation_message(self) -> str:
        return self._generation_message

    @generation_message.setter
    def generation_message(self, value: str) -> None:
        self._generation_message = value

    @property
    def personas(self) -> list:
        return self._personas

    @personas.setter
    def personas(self, value: list) -> None:
        self._personas = value

    @property
    def moderator_name(self) -> str:
        return self._moderator_name

    @moderator_name.setter
    def moderator_name(self, value: str) -> None:
        self._moderator_name = value

        self._synthesis: str = ""

    @property
    def synthesis(self) -> str:
        return self._synthesis

    @synthesis.setter
    def synthesis(self, value: str) -> None:
        self._synthesis = value

    def init_session_writer(self, personas_data: List[Dict[str, Any]]) -> None:
        from app.services.session_storage import SessionWriter

        self._session_writer = SessionWriter(
            session_id=self.id,
            topic=self.topic,
            personas=personas_data,
            max_messages=self.config.max_messages,
        )
        self.logger.log(
            "session", "storage_initialized", {"persona_count": len(personas_data)}
        )

    async def add_message(self, message: Message, count_toward_limit: bool = True) -> None:
        async with self._lock:
            self.conversation_log.append(message)
            if message.type in ("AGENT", "MODERATOR") and count_toward_limit:
                self._message_count += 1
            self._last_activity = datetime.now()

            event = AgentMessageEvent(
                agent_id=message.agent_id,
                agent_type=message.type,
                content=message.content,
                metadata={
                    "message_id": message.id,
                    "timestamp": message.timestamp.isoformat(),
                },
            )
            self.event_bus.publish(event)

        self.logger.log(
            "session",
            "message_added",
            {
                "agent_id": message.agent_id,
                "type": message.type,
                "content_preview": message.content[:80],
                "message_count": self._message_count,
            },
        )

        if self._session_writer:
            persona = self.agents.get(message.agent_id)
            agent_name = persona.name if hasattr(persona, "name") else message.agent_id
            self._session_writer.append_message(
                {
                    "id": message.id,
                    "agent_id": message.agent_id,
                    "agentName": agent_name,
                    "content": message.content,
                    "timestamp": message.timestamp.isoformat(),
                    "type": message.type,
                }
            )

    async def add_status_message(self, text: str) -> None:
        async with self._lock:
            message = Message(
                id=str(uuid.uuid4()),
                agent_id="system",
                content=text,
                timestamp=datetime.now(),
                type=MessageType.SYSTEM,
            )
            self.conversation_log.append(message)
            self._last_activity = datetime.now()

            event = AgentMessageEvent(
                agent_id="system",
                agent_type=MessageType.SYSTEM,
                content=text,
                metadata={
                    "message_id": message.id,
                    "timestamp": message.timestamp.isoformat(),
                },
            )
            self.event_bus.publish(event)

    def get_context_for_agent(
        self, agent_id: str, max_tokens: int = DEFAULT_TOKEN_LIMIT
    ) -> List[Dict[str, str]]:
        """
        Get windowed conversation history for an agent.

        Converts Message objects to dict format for LLM consumption.
        Uses token_counter to ensure context fits within token limit.

        Args:
            agent_id: The agent requesting context
            max_tokens: Maximum tokens to include (default: 8000)

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        if not self.conversation_log:
            return []

        messages_as_dicts = []
        for msg in self.conversation_log:
            role = "assistant" if msg.agent_id == agent_id else "user"
            messages_as_dicts.append(
                {
                    "role": role,
                    "content": f"[{msg.type}] {msg.content}",
                }
            )

        if count_tokens(messages_as_dicts) <= max_tokens:
            return messages_as_dicts

        windowed_messages = []
        for message in reversed(messages_as_dicts):
            test_messages = [message] + windowed_messages
            if count_tokens(test_messages) <= max_tokens:
                windowed_messages = [message] + windowed_messages
            else:
                break

        return windowed_messages

    def start_discussion(self) -> None:
        self.state = DiscussionState.ACTIVE
        self.phase = "INTRODUCTION"
        self._last_activity = datetime.now()
        self._paused = False
        self._stop_requested = False
        self._pause_event.set()
        self.logger.log(
            "session", "started", {"max_messages": self.config.max_messages}
        )

    def pause_discussion(self) -> None:
        self._paused = True
        self.state = DiscussionState.PAUSED
        self._pause_event.clear()
        self._last_activity = datetime.now()
        self.logger.log("session", "paused")

    def resume_discussion(self) -> None:
        self._paused = False
        self.state = DiscussionState.ACTIVE
        self._pause_event.set()
        self._last_activity = datetime.now()
        self.logger.log("session", "resumed")

    def stop_discussion(self) -> None:
        self._stop_requested = True
        self.state = DiscussionState.COMPLETED
        self.phase = "COMPLETED"
        self._pause_event.set()
        self.logger.log(
            "session",
            "stopped",
            {"message_count": self._message_count},
        )

    def finalize_session(self, synthesis: str) -> str:
        if self._session_writer:
            return self._session_writer.finalize(synthesis)
        return ""

    async def inject_instruction(self, instruction: str) -> None:
        self._inject_queue.put_nowait(instruction)
        self.logger.log(
            "session", "instruction_injected", {"instruction": instruction[:100]}
        )

    async def get_pending_inject(self) -> Optional[str]:
        try:
            return self._inject_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def cleanup(self) -> None:
        self._marked_for_cleanup = True
        self.state = DiscussionState.COMPLETED

    def is_marked_for_cleanup(self) -> bool:
        return self._marked_for_cleanup

    async def wait_if_paused(self) -> None:
        if self._paused:
            await self._pause_event.wait()

    def record_speaker(self, agent_id: str) -> None:
        self._speaker_history.append(agent_id)
        self._last_activity = datetime.now()

    def get_speaker_history(self, last_n: int = 10) -> List[str]:
        return self._speaker_history[-last_n:]

    def get_message_count(self) -> int:
        return self._message_count

    def is_paused(self) -> bool:
        return self._paused

    def should_stop(self) -> bool:
        return self._stop_requested or self._message_count >= self.config.max_messages

    def set_phase(self, phase: str) -> None:
        self.phase = phase

    def get_last_activity(self) -> datetime:
        """
        Get the timestamp of the last activity.

        Returns:
            datetime of last activity
        """
        return self._last_activity

    def add_agent(self, agent: BaseAgent) -> None:
        """
        Add an agent to the session.

        Args:
            agent: The agent to add
        """
        self.agents[agent.id] = agent

    def remove_agent(self, agent_id: str) -> None:
        """
        Remove an agent from the session.

        Args:
            agent_id: The ID of the agent to remove
        """
        if agent_id in self.agents:
            del self.agents[agent_id]

    def is_within_message_limit(self) -> bool:
        """
        Check if the discussion is within the message limit.

        Returns:
            True if within limit, False otherwise
        """
        return self.get_message_count() < self.config.max_messages

    def to_pydantic_model(self) -> "PydanticDiscussionSession":
        """
        Convert to Pydantic model for serialization.

        Returns:
            Pydantic DiscussionSession model
        """
        from app.models.discussion import DiscussionSession as PydanticDiscussionSession
        from app.models.agent import Agent

        agent_models = []
        for agent in self.agents.values():
            agent_models.append(
                Agent(
                    id=agent.id,
                    name=agent.name,
                    role="",  # BaseAgent doesn't have role field
                    background="",  # BaseAgent doesn't have background field
                    stance="",  # BaseAgent doesn't have stance field
                    type=agent.type,
                )
            )

        return PydanticDiscussionSession(
            id=self.id,
            topic=self.topic,
            state=self.state,
            conversation_log=self.conversation_log,
            agents=agent_models,
            config=self.config,
        )
