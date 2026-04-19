"""Integration tests for the EventBus."""

import pytest
from app.orchestration.event_bus import (
    EventBus,
    AgentMessageEvent,
    FactCheckEvent,
    ModeratorCommandEvent,
    StallDetectedEvent,
)


class TestEventBus:
    """Test suite for EventBus."""

    def test_event_publishing_and_receiving(self):
        """Test that events are published and received by subscribers."""
        bus = EventBus(max_history_size=100)
        received_events = []

        def handler(event):
            received_events.append(event)

        bus.subscribe("agent_message", handler)

        event = AgentMessageEvent(
            agent_id="agent_1", agent_type="participant", content="Hello world"
        )
        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].agent_id == "agent_1"
        assert received_events[0].content == "Hello world"

    def test_multiple_subscribers_receive_same_event(self):
        """Test that multiple subscribers receive the same event."""
        bus = EventBus(max_history_size=100)
        received_by_handler1 = []
        received_by_handler2 = []

        def handler1(event):
            received_by_handler1.append(event)

        def handler2(event):
            received_by_handler2.append(event)

        bus.subscribe("fact_check", handler1)
        bus.subscribe("fact_check", handler2)

        event = FactCheckEvent(
            claim="The sky is blue", source="observation", result=True, confidence=0.95
        )
        bus.publish(event)

        assert len(received_by_handler1) == 1
        assert len(received_by_handler2) == 1
        assert received_by_handler1[0] is received_by_handler2[0]

    def test_history_limit_enforced(self):
        """Test that history limit is enforced (max_history_size)."""
        max_history = 5
        bus = EventBus(max_history_size=max_history)

        for i in range(10):
            event = AgentMessageEvent(
                agent_id=f"agent_{i}", agent_type="participant", content=f"Message {i}"
            )
            bus.publish(event)

        history = bus.get_history()
        assert len(history) == max_history
        assert history[0].agent_id == "agent_5"
        assert history[-1].agent_id == "agent_9"

    def test_unsubscribe_works_correctly(self):
        """Test that unsubscribe removes the handler."""
        bus = EventBus(max_history_size=100)
        received_events = []

        def handler(event):
            received_events.append(event)

        bus.subscribe("moderator_command", handler)

        event1 = ModeratorCommandEvent(command="start")
        bus.publish(event1)
        assert len(received_events) == 1

        bus.unsubscribe("moderator_command", handler)

        event2 = ModeratorCommandEvent(command="stop")
        bus.publish(event2)
        assert len(received_events) == 1

    def test_different_event_types(self):
        """Test that different event types work correctly."""
        bus = EventBus(max_history_size=100)

        agent_msg_received = []
        fact_check_received = []
        moderator_cmd_received = []
        stall_detected_received = []

        bus.subscribe("agent_message", lambda e: agent_msg_received.append(e))
        bus.subscribe("fact_check", lambda e: fact_check_received.append(e))
        bus.subscribe("moderator_command", lambda e: moderator_cmd_received.append(e))
        bus.subscribe("stall_detected", lambda e: stall_detected_received.append(e))

        bus.publish(AgentMessageEvent(agent_id="a1", agent_type="p", content="msg"))
        bus.publish(FactCheckEvent(claim="test"))
        bus.publish(ModeratorCommandEvent(command="test"))
        bus.publish(StallDetectedEvent(agent_id="a1", reason="timeout"))

        assert len(agent_msg_received) == 1
        assert len(fact_check_received) == 1
        assert len(moderator_cmd_received) == 1
        assert len(stall_detected_received) == 1

    def test_clear_history(self):
        """Test that clear_history removes all events."""
        bus = EventBus(max_history_size=100)

        for i in range(5):
            bus.publish(
                AgentMessageEvent(
                    agent_id=f"agent_{i}",
                    agent_type="participant",
                    content=f"Message {i}",
                )
            )

        assert len(bus.get_history()) == 5

        bus.clear_history()

        assert len(bus.get_history()) == 0

    def test_max_history_size_property(self):
        """Test that max_history_size property returns correct value."""
        bus = EventBus(max_history_size=50)
        assert bus.max_history_size == 50

        bus2 = EventBus()
        assert bus2.max_history_size == 100
