from typing import TYPE_CHECKING

from app.utils.language import detect_language

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent


class ConvergenceDetector:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator

    async def check(self, personas: list) -> bool:
        if not self._mod.session:
            return False

        if self._mod.session.get_message_count() >= self._mod.session.config.max_messages:
            return True

        context = self._mod.session.get_context_for_agent(self._mod.id)
        if not context:
            return False

        topic = self._mod.session.topic if self._mod.session else "Unknown topic"
        language = detect_language(topic)

        convergence_prompt = f"""Analyze the conversation and determine if the discussion has converged.

Respond in {language}.

Return ONLY one of these responses:
- CONVERGED: if participants are repeating arguments, no new perspectives, discussion exhausted
- CONTINUE: if there are still new arguments to explore, perspectives not fully discussed

Consider:
1. Are participants repeating the same arguments?
2. Have all major perspectives been explored?
3. Is there genuine engagement or just agreement/disagreement?
4. Has the discussion reached a natural conclusion?

Conversation context:
"""
        convergence_context = [{"role": "system", "content": convergence_prompt}]
        convergence_context.extend(context[-10:])

        full_response = (await self._mod._stream_llm(convergence_context)).upper()
        return "CONVERGED" in full_response
