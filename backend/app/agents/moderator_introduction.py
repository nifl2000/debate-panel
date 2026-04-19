import asyncio
from typing import TYPE_CHECKING

from app.models.message import MessageType

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent


class IntroductionRound:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator

    async def run(self, personas: list) -> None:
        session = self._mod.session
        if not session or not personas:
            return

        session.logger.log(
            "moderator", "introduction_starting", {"persona_count": len(personas)}
        )
        await session.add_status_message("👋 Introduction round...")

        for persona in personas:
            await session.wait_if_paused()
            if session.should_stop():
                session.logger.log(
                    "moderator", "introduction_aborted", {"reason": "should_stop"}
                )
                return

            await session.add_status_message(
                f"🎤 {persona.name} stellt sich vor..."
            )
            session.logger.log(
                "moderator", "persona_introducing", {"persona": persona.name}
            )

            try:
                intro = await persona.introduce()
                await session.add_message(intro, count_toward_limit=False)
                session.record_speaker(persona.id)
                session.logger.log(
                    "moderator",
                    "persona_introduced",
                    {
                        "persona": persona.name,
                        "intro_length": len(intro.content),
                    },
                )
            except Exception as e:
                await session.add_status_message(f"❌ {persona.name}: {str(e)}")
                session.logger.log_error(
                    "moderator", str(e), {"persona": persona.name}
                )

            await asyncio.sleep(0.5)

        session._introduction_done = True
        session.logger.log(
            "moderator",
            "introduction_completed",
            {"personas_introduced": len(personas)},
        )
        await session.add_status_message("✅ Introduction round complete")
