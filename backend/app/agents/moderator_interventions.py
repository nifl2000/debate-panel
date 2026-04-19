"""Intervention logic extracted from ModeratorAgent."""

import asyncio
from typing import TYPE_CHECKING

from app.llm.prompts import MODERATOR_SPEAKING_PROMPT
from app.models.message import MessageType
from app.utils.language import detect_language

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent

_INTERVENTION_EMOJI = {
    "CLARIFYING": "🔍",
    "PROVOCATIVE": "🔥",
    "SUMMARIZING": "📋",
    "REDIRECTING": "🎯",
}

_AGREEMENT_WORDS = [
    "zustimmung",
    "genau",
    "richtig",
    "einig",
    "agree",
    "exactly",
]


class InterventionHandler:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator

    async def speak(self) -> None:
        session = self._mod.session
        if not session:
            return

        language = detect_language(session.topic)
        intervention_type = self._choose_type()
        session.logger.log(
            "moderator", "intervention_type_chosen", {"type": intervention_type}
        )

        recent = session.conversation_log[-8:]
        recent_text = "\n".join(m.content for m in recent if m.type != "SYSTEM")

        prompt = MODERATOR_SPEAKING_PROMPT(
            topic=session.topic,
            language=language,
            intervention_type=intervention_type,
            recent_conversation=recent_text,
        )

        try:
            full_content = await self._mod._stream_llm(
                [{"role": "user", "content": prompt}]
            )
        except Exception:
            return

        if not full_content or len(full_content) < 10:
            full_content = "As moderator I would like to ask: Can we look at this more closely?"

        mod_message = self._mod._create_message(full_content, MessageType.MODERATOR)
        await session.add_message(mod_message)
        session.record_speaker(self._mod.id)

        emoji = _INTERVENTION_EMOJI.get(intervention_type, "🎙️")
        await session.add_status_message(f"{emoji} Moderator ({intervention_type})")

    def _choose_type(self) -> str:
        session = self._mod.session
        if not session:
            return "CLARIFYING"

        recent = session.conversation_log[-10:]
        recent_text = " ".join(m.content.lower() for m in recent if m.type != "SYSTEM")

        if len(recent) >= 6:
            unique = len(set(m.agent_id for m in recent if m.agent_id != "system"))
            if unique <= 2:
                return "REDIRECTING"

        if any(w in recent_text for w in _AGREEMENT_WORDS):
            return "PROVOCATIVE"

        if session.get_message_count() % 8 == 0:
            return "SUMMARIZING"

        return "CLARIFYING"

    async def process_injection(self, instruction: str) -> None:
        session = self._mod.session
        if not session:
            return

        language = detect_language(session.topic)
        context = "\n".join(
            f"{msg.agent_id}: {msg.content}" for msg in session.conversation_log[-10:]
        )

        prompt = (
            f"You are the moderator of a debate panel. The user has given you this instruction:\n\n"
            f"USER INSTRUCTION: {instruction}\n\n"
            f"CURRENT DISCUSSION CONTEXT:\n{context}\n\n"
            f"TOPIC: {session.topic}\n\n"
            f"OUTPUT LANGUAGE: {language}\n\n"
            f"TASK: Acknowledge the user's instruction and explain how you will implement it "
            f"in the discussion. Be brief (2-3 sentences). Speak naturally as a moderator "
            f"addressing the panel.\n\n"
            f"FORMATTING: Plain text only. No markdown, bold, italics, or special formatting."
        )

        try:
            full_content = await self._mod._stream_llm(
                [{"role": "user", "content": prompt}]
            )
        except Exception:
            full_content = (
                f"Verstanden. Ich werde Ihre Anweisung beachten: {instruction}"
            )

        if not full_content or len(full_content) < 10:
            full_content = (
                f"Verstanden. Ich werde Ihre Anweisung beachten: {instruction}"
            )

        inject_message = self._mod._create_message(
            f"💬 Benutzer-Anweisung: {instruction}\n\n{full_content}",
            MessageType.MODERATOR,
        )
        await session.add_message(inject_message)
        session.record_speaker(self._mod.id)
        await session.add_status_message(
            f"💬 Anweisung injiziert: {instruction[:50]}..."
        )

    async def check_intervention(self, personas: list) -> None:
        session = self._mod.session
        if not session or session.get_message_count() < 6:
            return

        last = session.conversation_log[-8:]
        unique = len(set(m.agent_id for m in last if m.agent_id != "system"))
        if unique <= 2 and len(last) >= 6:
            await session.add_status_message("🎯 Moderator intervenes...")
            await asyncio.sleep(0.5)
