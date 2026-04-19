"""Reflection round: moderator asks each persona for their takeaways before synthesis."""

import asyncio
from typing import TYPE_CHECKING

from app.llm.prompts import REFLECTION_QUESTION_PROMPT, REFLECTION_RESPONSE_PROMPT
from app.models.message import MessageType
from app.utils.language import detect_language

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent


class ReflectionRound:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator

    async def run(self, personas: list) -> None:
        session = self._mod.session
        if not session or not personas:
            return

        session.logger.log(
            "moderator",
            "reflection_started",
            {"persona_count": len(personas)},
        )
        await session.add_status_message("💭 Reflection round...")

        # Step 1: Moderator poses the reflection question to the panel
        language = detect_language(session.topic)
        question_prompt = REFLECTION_QUESTION_PROMPT(
            topic=session.topic,
            language=language,
        )

        try:
            question_content = await self._mod._stream_llm(
                [{"role": "user", "content": question_prompt}]
            )
        except Exception:
            question_content = (
                f"What are you taking away from this discussion? "
                f"What did you learn? Which questions remain open?"
            )

        question_message = self._mod._create_message(question_content, MessageType.MODERATOR)
        await session.add_message(question_message, count_toward_limit=False)
        session.record_speaker(self._mod.id)

        await asyncio.sleep(0.3)

        # Step 2: Each persona reflects in turn
        for persona in personas:
            await session.wait_if_paused()
            if session._stop_requested:
                session.logger.log(
                    "moderator", "reflection_aborted", {"reason": "should_stop"}
                )
                return

            await session.add_status_message(f"💭 {persona.name} reflects...")
            session.logger.log(
                "moderator", "persona_reflecting", {"persona": persona.name}
            )

            try:
                reflection_prompt = REFLECTION_RESPONSE_PROMPT(
                    name=persona.name,
                    role=persona.role,
                    background=persona.background,
                    stance=persona.stance,
                    topic=session.topic,
                    language=language,
                )

                reflection_content = await asyncio.wait_for(
                    persona._stream_llm([{"role": "user", "content": reflection_prompt}]),
                    timeout=60,
                )

                reflection_message = persona._create_message(
                    reflection_content, MessageType.AGENT
                )
                await session.add_message(reflection_message, count_toward_limit=False)
                session.record_speaker(persona.id)

                session.logger.log(
                    "moderator",
                    "persona_reflected",
                    {
                        "persona": persona.name,
                        "reflection_length": len(reflection_content),
                    },
                )
            except Exception as e:
                await session.add_status_message(f"❌ {persona.name}: {str(e)}")
                session.logger.log_error(
                    "moderator", str(e), {"persona": persona.name}
                )

            await asyncio.sleep(0.3)

        session.logger.log(
            "moderator",
            "reflection_completed",
            {"personas_reflected": len(personas)},
        )
        await session.add_status_message("✅ Reflection round complete")
