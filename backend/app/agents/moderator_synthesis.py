"""Synthesis generation extracted from ModeratorAgent."""

from typing import TYPE_CHECKING

from app.llm.prompts import SYNTHESIS_PROMPT
from app.models.message import MessageType
from app.utils.language import detect_language

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent


class SynthesisGenerator:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator

    async def generate(self, personas: list) -> None:
        session = self._mod.session
        if not session or not session.conversation_log:
            return

        session.logger.log(
            "moderator",
            "synthesis_started",
            {
                "conversation_length": len(session.conversation_log),
            },
        )
        await session.add_status_message("📝 Moderator writing summary...")

        language = detect_language(session.topic)
        panel_overview = "\n".join(
            f"- {p.name} ({p.role}): {p._stance}" for p in personas
        )
        conversation_text = "\n".join(
            f"{msg.agent_id}: {msg.content}" for msg in session.conversation_log
        )

        prompt = SYNTHESIS_PROMPT(
            topic=session.topic,
            conversation=conversation_text,
            language=language,
        )

        try:
            full_content = await self._mod._stream_llm(
                [{"role": "user", "content": prompt}]
            )
        except Exception:
            full_content = (
                f"Summary of the discussion: {session.topic}\n\n"
                f"The discussion explored various perspectives."
            )

        if not full_content or len(full_content) < 20:
            full_content = (
                f"Summary of the discussion: {session.topic}\n\n"
                f"The discussion explored various perspectives."
            )

        synthesis_message = self._mod._create_message(
            full_content, MessageType.MODERATOR
        )
        await session.add_message(synthesis_message, count_toward_limit=False)
        session.record_speaker(self._mod.id)
        await session.add_status_message("📋 Summary complete")
