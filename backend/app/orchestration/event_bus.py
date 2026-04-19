"""Event bus for agent communication using bubus library."""

from collections import deque
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import Field
from bubus import BaseEvent


class AgentMessageEvent(BaseEvent):
    """Event emitted when an agent generates a message."""

    agent_id: str
    agent_type: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FactCheckEvent(BaseEvent):
    """Event emitted when a fact-check is requested or completed."""

    claim: str
    source: Optional[str] = None
    result: Optional[bool] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModeratorCommandEvent(BaseEvent):
    """Event emitted when a moderator issues a command."""

    command: str
    target_agent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StallDetectedEvent(BaseEvent):
    """Event emitted when a stall is detected in the discussion."""

    agent_id: str
    reason: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


REVERSE_EVENT_TYPE_MAP: Dict[Type[BaseEvent], str] = {
    AgentMessageEvent: "agent_message",
    FactCheckEvent: "fact_check",
    ModeratorCommandEvent: "moderator_command",
    StallDetectedEvent: "stall_detected",
}


class EventBus:
    """
    Event bus for agent communication.

    Uses bubus BaseEvent for event definitions and provides:
    - Event publishing and subscribing
    - History tracking with configurable limit
    - FIFO processing order
    """

    def __init__(self, max_history_size: int = 100):
        """
        Initialize the event bus.

        Args:
            max_history_size: Maximum number of events to keep in history.
                              Defaults to 100 to prevent memory leaks.
        """
        self._max_history_size = max_history_size
        self._history: deque = deque(maxlen=max_history_size)
        self._subscriptions: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable[[BaseEvent], None]) -> None:
        """
        Subscribe to an event type.

        Args:
            event_type: The type of event to subscribe to
            handler: Callback function to handle the event
        """
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []

        if handler not in self._subscriptions[event_type]:
            self._subscriptions[event_type].append(handler)

    def unsubscribe(
        self, event_type: str, handler: Callable[[BaseEvent], None]
    ) -> None:
        """
        Unsubscribe from an event type.

        Args:
            event_type: The type of event to unsubscribe from
            handler: The handler to remove
        """
        if event_type in self._subscriptions:
            if handler in self._subscriptions[event_type]:
                self._subscriptions[event_type].remove(handler)

    def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to all subscribers.

        Events are processed in FIFO order.

        Args:
            event: The event to publish (must be a bubus BaseEvent)
        """
        self._history.append(event)

        event_type = REVERSE_EVENT_TYPE_MAP.get(type(event), type(event).__name__)
        if event_type in self._subscriptions:
            for handler in self._subscriptions[event_type]:
                handler(event)

    def get_history(self) -> List[BaseEvent]:
        """
        Get the event history.

        Returns:
            List of events in FIFO order (oldest first)
        """
        return list(self._history)

    def clear_history(self) -> None:
        """Clear the event history."""
        self._history.clear()

    @property
    def max_history_size(self) -> int:
        """Get the maximum history size."""
        return self._max_history_size
