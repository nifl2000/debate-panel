"""Event handler for ModeratorAgent — consolidates event bus subscriptions."""

import asyncio
from typing import TYPE_CHECKING

from app.models.message import Message, MessageType

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent


class EventHandler:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator

    def handle_agent_message(self, event) -> None:
        if not self._mod.session:
            return

        agent_id = event.agent_id
        self._mod._last_speaker_id = agent_id
        self._mod._speaker_counts[agent_id] = self._mod._speaker_counts.get(agent_id, 0) + 1

        if self._mod.stall_detector:
            stall_info = self._mod.stall_detector.detect_stall(
                self._mod.session.conversation_log,
                None,
            )
            if stall_info:
                from app.orchestration.event_bus import StallDetectedEvent
                stall_event = StallDetectedEvent(
                    agent_id=self._mod.id,
                    reason=stall_info.reason,
                    metadata={
                        "signals": stall_info.signals,
                        "suggestion": stall_info.suggestion,
                    },
                )
                self._mod.session.event_bus.publish(stall_event)

        if self._mod.fact_checker and str(event.agent_type) == "PERSONA":
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._mod.factcheck.detect_and_check(event.content))
            except RuntimeError:
                pass

    def handle_fact_check(self, event) -> None:
        if event.result is not None:
            self._mod._pending_fact_checks.append(event)
            try:
                asyncio.get_running_loop()
                asyncio.create_task(self._mod.factcheck._integrate(event))
            except RuntimeError:
                pass

    def handle_stall_detected(self, event) -> None:
        if not self._mod.session:
            return

        suggestion = event.metadata.get("suggestion", "Let's explore a new angle.")
        message = self._mod._create_message(suggestion, MessageType.MODERATOR)
        asyncio.create_task(self._mod.session.add_message(message))
