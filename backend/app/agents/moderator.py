"""
ModeratorAgent - Orchestrates the entire discussion flow.

The moderator is the central orchestrator that:
- Subscribes to all events from the event bus
- Triggers stall detection and intervention
- Selects the next speaker
- Integrates fact-checks at optimal moments
- Detects convergence and generates synthesis

This file delegates to extracted handler classes:
- InterventionHandler: moderator interventions
- SynthesisGenerator: final synthesis
- FactCheckIntegrator: fact-check integration
"""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

from app.agents.base import BaseAgent
from app.agents.moderator_interventions import InterventionHandler
from app.agents.moderator_synthesis import SynthesisGenerator
from app.agents.moderator_reflection import ReflectionRound
from app.agents.moderator_factcheck import FactCheckIntegrator
from app.agents.moderator_introduction import IntroductionRound
from app.agents.moderator_speaker_selector import SpeakerSelector
from app.agents.moderator_convergence import ConvergenceDetector
from app.agents.moderator_events import EventHandler
from app.llm.client import LLMClient
from app.utils.language import detect_language
from app.llm.prompts import MODERATOR_PROMPT, SYNTHESIS_PROMPT
from app.models.agent import AgentType
from app.models.message import Message, MessageType
from app.orchestration.event_bus import (
    AgentMessageEvent,
    EventBus,
    FactCheckEvent,
    StallDetectedEvent,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from app.orchestration.session import DiscussionSession
    from app.orchestration.stall_detector import StallDetector, StallInfo
    from app.agents.fact_checker import FactCheckerAgent


class StallDetectorProtocol(Protocol):
    """Protocol for StallDetector to allow mock implementations."""

    def detect_stall(
        self, conversation_log: List[Message], last_message_time: datetime
    ) -> Optional["StallInfo"]:
        """Detect if discussion is stalling."""
        ...

    def get_intervention_suggestion(self, stall_info: "StallInfo") -> str:
        """Get intervention suggestion for stall."""
        ...


class FactCheckerProtocol(Protocol):
    """Protocol for FactCheckerAgent to allow mock implementations."""

    async def detect_claims(self, message: str) -> List[str]:
        """Detect factual claims in a message."""
        ...

    async def check_claim(self, claim: str) -> Optional[FactCheckEvent]:
        """Check a claim asynchronously."""
        ...


class ModeratorAgent(BaseAgent):
    """
    Agent that orchestrates the entire discussion flow.

    The moderator:
    - Monitors all events via the event bus
    - Triggers stall detection on AgentMessageEvent
    - Selects the next speaker based on conversation dynamics
    - Integrates fact-checks at optimal moments
    - Detects convergence to end discussion
    - Generates synthesis at discussion end

    The moderator does NOT:
    - Directly command personas (injects prompt suggestions only)
    - Block discussion for fact-checks (async integration)
    - Intervene on single stall signal (requires 2+ signals)
    """

    def __init__(
        self,
        id: str,
        name: str,
        llm_client: LLMClient,
        session: Optional["DiscussionSession"] = None,
        stall_detector: Optional[StallDetectorProtocol] = None,
        fact_checker: Optional[FactCheckerProtocol] = None,
        emoji: str = "🎙️",
    ) -> None:
        """
        Initialize the moderator agent.

        Args:
            id: Unique identifier for the agent
            name: Display name of the moderator
            llm_client: LLM client instance for generating responses
            session: Optional discussion session for context access
            stall_detector: StallDetector instance for detecting stalls
            fact_checker: FactCheckerAgent instance for checking claims
        """
        super().__init__(
            id=id,
            name=name,
            type=AgentType.MODERATOR,
            llm_client=llm_client,
            session=session,
        )
        self.stall_detector = stall_detector
        self.fact_checker = fact_checker
        self.emoji = emoji
        self._pending_fact_checks: List[FactCheckEvent] = []
        self._checked_claims: set = set()
        self._last_speaker_id: Optional[str] = None
        self._speaker_counts: Dict[str, int] = {}
        self._running: bool = False
        self._moderator_task: Optional[asyncio.Task] = None

        self.interventions = InterventionHandler(self)
        self.synthesis = SynthesisGenerator(self)
        self.reflection = ReflectionRound(self)
        self.factcheck = FactCheckIntegrator(self)
        self.introduction = IntroductionRound(self)
        self.speaker_selector = SpeakerSelector(self)
        self.convergence = ConvergenceDetector(self)
        self.events = EventHandler(self)

    async def generate_response(self, context: list[dict]) -> Message:
        """
        Generate a response based on the conversation context.

        Uses MODERATOR_PROMPT to format the system prompt.

        Args:
            context: List of message dictionaries with 'role' and 'content'

        Returns:
            Message object containing the moderator's response
        """
        topic = self.session.topic if self.session else "Unknown topic"
        panel_size = len(self.session.agents) if self.session else 0
        max_messages = self.session.config.max_messages if self.session else 20

        language = detect_language(topic)

        system_prompt = MODERATOR_PROMPT(
            topic=topic,
            panel_size=panel_size,
            max_messages=max_messages,
            language=language,
        )

        formatted_messages = self._format_messages_for_llm(context, system_prompt)

        full_content = await self._stream_llm(formatted_messages)

        if not full_content or len(full_content) < 10:
            full_content = (
            "As moderator I would like to point out, "
            "that we should stay on topic. Let's continue the discussion."
            )

        return self._create_message(full_content, MessageType.MODERATOR)

    async def moderator_loop(self) -> None:
        if not self.session:
            return

        self._running = True
        event_bus = self.session.event_bus

        event_bus.subscribe("agent_message", self.events.handle_agent_message)
        event_bus.subscribe("fact_check", self.events.handle_fact_check)
        event_bus.subscribe("stall_detected", self.events.handle_stall_detected)

        personas = [a for a in self.session.agents.values() if hasattr(a, "stance")]
        self.session.logger.log(
            "moderator",
            "loop_started",
            {
                "persona_count": len(personas),
                "persona_names": [p.name for p in personas],
            },
        )

        try:
            await self.session.add_status_message("🎬 Starting discussion...")
            await asyncio.sleep(1)

            self.session.logger.log("moderator", "starting_introduction_round")
            await self.introduction.run(personas)
            self.session.logger.log("moderator", "introduction_completed")

            self.session.set_phase("DISCUSSION")
            self.session.logger.log(
                "moderator", "phase_changed", {"phase": "DISCUSSION"}
            )
            await self.session.add_status_message("💬 Open discussion begins...")
            await asyncio.sleep(1)

            messages_since_moderator = 0
            moderator_interval = 3
            loop_iteration = 0
            moderator_cooldown = 0

            while not self.session.should_stop() and self._running:
                loop_iteration += 1
                self.session.logger.log(
                    "moderator",
                    "loop_iteration",
                    {
                        "iteration": loop_iteration,
                        "message_count": self.session.get_message_count(),
                        "should_stop": self.session.should_stop(),
                        "running": self._running,
                    },
                )

                await self.session.wait_if_paused()

                if self.session.should_stop():
                    self.session.logger.log(
                        "moderator", "loop_stopped", {"reason": "should_stop"}
                    )
                    break

                if moderator_cooldown > 0:
                    moderator_cooldown -= 1

                if (
                    messages_since_moderator >= moderator_interval
                    and moderator_cooldown == 0
                ):
                    self.session.logger.log(
                        "moderator",
                        "moderator_speaking",
                        {"messages_since_last": messages_since_moderator},
                    )
                    await self.interventions.speak()
                    messages_since_moderator = 0
                    moderator_cooldown = 2

                next_speaker = self.speaker_selector.select(personas)
                if not next_speaker:
                    self.session.logger.log(
                        "moderator", "no_speaker_selected", {"reason": "breaking"}
                    )
                    break

                self.session.logger.log(
                    "moderator",
                    "speaker_selected",
                    {
                        "speaker_name": next_speaker.name,
                        "speaker_id": next_speaker.id,
                    },
                )

                await self.session.wait_if_paused()
                if self.session.should_stop():
                    break

                await self.session.add_status_message(
                    f"🎤 {next_speaker.name} spricht..."
                )

                try:
                    context = self.session.get_context_for_agent(next_speaker.id)
                    self.session.logger.log(
                        "moderator",
                        "generating_response",
                        {
                            "speaker": next_speaker.name,
                            "context_messages": len(context),
                        },
                    )
                    response = await next_speaker.generate_response(context)
                    await self.session.add_message(response)
                    self.session.record_speaker(next_speaker.id)
                    messages_since_moderator += 1
                    self.session.logger.log(
                        "moderator",
                        "response_added",
                        {
                            "speaker": next_speaker.name,
                            "total_messages": self.session.get_message_count(),
                            "messages_since_moderator": messages_since_moderator,
                        },
                    )
                except Exception as e:
                    await self.session.add_status_message(
                        f"❌ {next_speaker.name}: {str(e)}"
                    )
                    self.session.logger.log_error(
                        "moderator",
                        str(e),
                        {
                            "speaker": next_speaker.name,
                        },
                    )

                await self.interventions.check_intervention(personas)

                if (
                    loop_iteration % 5 == 0
                    and self.session.get_message_count()
                    >= self.session.config.max_messages - 2
                ):
                    converged = await self.convergence.check(personas)
                    if converged:
                        self.session.logger.log("moderator", "convergence_detected")
                        break

                inject_instruction = await self.session.get_pending_inject()
                if inject_instruction:
                    await self.interventions.process_injection(inject_instruction)

                await asyncio.sleep(0.5)

            self.session.logger.log(
                "moderator",
                "loop_ended",
                {
                    "total_iterations": loop_iteration,
                    "total_messages": self.session.get_message_count(),
                    "reason": "should_stop"
                    if self.session.should_stop()
                    else "no_speaker_or_not_running",
                },
            )

            await self.reflection.run(personas)
            await self.synthesis.generate(personas)

            await self.session.add_status_message("✅ Discussion completed")
            self.session.stop_discussion()
        except Exception as e:
            self.session.logger.log_error(
                "moderator",
                f"Loop crashed: {str(e)}",
                {
                    "iteration": loop_iteration if "loop_iteration" in locals() else 0,
                    "message_count": self.session.get_message_count(),
                },
            )
            import traceback

            self.session.logger.log_error("moderator", traceback.format_exc())
            await self.session.add_status_message(f"❌ Error: {str(e)}")
        finally:
            self._running = False
            self.session.logger.log("moderator", "cleanup", {"running": False})
            event_bus.unsubscribe("agent_message", self.events.handle_agent_message)
            event_bus.unsubscribe("fact_check", self.events.handle_fact_check)
            event_bus.unsubscribe("stall_detected", self.events.handle_stall_detected)

    def start_loop(self) -> None:
        """Start the moderator loop as a background task."""
        if self._moderator_task is None or self._moderator_task.done():
            self._moderator_task = asyncio.create_task(self.moderator_loop())

    def stop_loop(self) -> None:
        """Stop the moderator loop."""
        self._running = False
        if self._moderator_task and not self._moderator_task.done():
            self._moderator_task.cancel()

    def resume_loop(self) -> None:
        """Resume the moderator loop after pause."""
        if not self._running and (
            not self._moderator_task or self._moderator_task.done()
        ):
            self._running = True
            self._moderator_task = asyncio.create_task(self.moderator_loop())

    def _handle_agent_message_event(self, event) -> None:
        self.events.handle_agent_message(event)

    def _handle_fact_check_event(self, event) -> None:
        self.events.handle_fact_check(event)

    def _handle_stall_detected_event(self, event) -> None:
        self.events.handle_stall_detected(event)

    async def detect_convergence(self) -> bool:
        if not self.session:
            return False
        return await self.convergence.check([])

    async def generate_synthesis(self) -> Message:
        """
        Generate final synthesis/summary of the discussion.

        Uses SYNTHESIS_PROMPT to create a comprehensive summary.

        Returns:
            Message containing the synthesis
        """
        if not self.session:
            return self._create_message(
                "No discussion to synthesize.", MessageType.MODERATOR
            )

        conversation_text = "\n".join(
            f"[{msg.type}] {msg.content}" for msg in self.session.conversation_log
        )

        topic = self.session.topic if self.session else "Unknown topic"
        language = detect_language(topic)

        synthesis_prompt = SYNTHESIS_PROMPT(
            topic=topic,
            conversation=conversation_text,
            language=language,
        )

        formatted_messages = [{"role": "system", "content": synthesis_prompt}]

        full_content = await self._stream_llm(formatted_messages)

        message = self._create_message(full_content, MessageType.MODERATOR)
        await self.session.add_message(message)

        return message

    def select_next_speaker(self) -> Optional[str]:
        """
        Select which persona should speak next.

        Selection criteria:
        - Prioritize personas who haven't spoken recently
        - Consider conversation dynamics (who has relevant expertise)
        - Avoid same speaker consecutively
        - Balance participation across all personas

        Returns:
            Agent ID of the selected speaker, or None if no personas available
        """
        if not self.session:
            return None

        persona_agents = [
            agent_id
            for agent_id, agent in self.session.agents.items()
            if agent.type == AgentType.PERSONA
        ]

        if not persona_agents:
            return None

        if len(persona_agents) == 1:
            return persona_agents[0]

        scored_agents: Dict[str, float] = {}
        for agent_id in persona_agents:
            score = 0.0

            if agent_id == self._last_speaker_id:
                score -= 10.0

            speak_count = self._speaker_counts.get(agent_id, 0)
            score -= speak_count * 2.0

            min_speak_count = min(
                self._speaker_counts.get(aid, 0) for aid in persona_agents
            )
            if speak_count == min_speak_count:
                score += 5.0

            scored_agents[agent_id] = score

        best_agent = max(scored_agents.items(), key=lambda x: x[1])
        return best_agent[0]

    def get_pending_fact_checks(self) -> List[FactCheckEvent]:
        """
        Get list of pending fact-checks awaiting integration.

        Returns:
            List of FactCheckEvent objects
        """
        return self._pending_fact_checks.copy()

    def clear_pending_fact_checks(self) -> None:
        """Clear all pending fact-checks."""
        self._pending_fact_checks.clear()

    async def integrate_fact_check(self, fact_check: FactCheckEvent) -> Message:
        """
        Integrate a fact-check result into the discussion.

        Creates a moderator message presenting the fact-check result.

        Args:
            fact_check: The FactCheckEvent to integrate

        Returns:
            Message containing the fact-check integration
        """
        verdict_text = self._format_fact_check_verdict(fact_check)
        message = self._create_message(verdict_text, MessageType.FACT_CHECK)

        if self.session:
            await self.session.add_message(message)

        return message

    def _format_fact_check_verdict(self, fact_check: FactCheckEvent) -> str:
        """
        Format a fact-check result for presentation.

        Args:
            fact_check: The FactCheckEvent to format

        Returns:
            Formatted string for the fact-check verdict
        """
        verdict = "Verified" if fact_check.result else "Unverified"
        confidence = (
            f" (Confidence: {fact_check.confidence:.0%})"
            if fact_check.confidence
            else ""
        )
        source = f" Source: {fact_check.source}" if fact_check.source else ""

        return f"Fact-check: {fact_check.claim} - {verdict}{confidence}{source}"

    async def _inject_intervention(self, suggestion: str) -> None:
        """
        Inject a prompt suggestion to redirect discussion.

        Creates a moderator message with the suggestion and adds it to the log.

        Args:
            suggestion: The intervention suggestion
        """
        if not self.session:
            return

        message = self._create_message(suggestion, MessageType.MODERATOR)
        await self.session.add_message(message)

    async def _check_convergence(self) -> None:
        """
        Check if discussion has converged using LLM judgment.
        """
        if not self.session:
            return

        converged = await self.detect_convergence()
        if converged:
            await self.generate_synthesis()
            self.session.stop_discussion()
            self.stop_loop()
