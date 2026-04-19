"""Fact-check integration extracted from ModeratorAgent."""

import asyncio
from typing import TYPE_CHECKING, List

from app.models.message import MessageType
from app.orchestration.event_bus import FactCheckEvent

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent

_VERDICT_EMOJI = {
    "verified": "🟢",
    "disputed": "🟡",
    "unverified": "⚪",
    "refuted": "🔴",
    "mixed": "🟣",
}
_VERDICT_LABEL = {
    "verified": "Verified",
    "disputed": "Umstritten",
    "unverified": "Nicht verifizierbar",
    "refuted": "Widerlegt",
        "mixed": "Mixed",
}


class FactCheckIntegrator:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator
        self._pending: List[FactCheckEvent] = []
        self._checked_claims: set = set()

    def handle_event(self, event: FactCheckEvent) -> None:
        if event.result is not None:
            self._pending.append(event)
            asyncio.create_task(self._integrate(event))

    async def detect_and_check(self, content: str) -> None:
        fc = self._mod.fact_checker
        session = self._mod.session
        if not fc or not session or session.phase == "INTRODUCTION":
            return
        try:
            claims = await fc.detect_claims(content)
            for claim in claims:
                claim_key = claim.strip().lower()
                if claim_key not in self._checked_claims:
                    self._checked_claims.add(claim_key)
                    asyncio.create_task(self._check_claim(claim))
        except Exception:
            pass

    async def _check_claim(self, claim: str) -> None:
        fc = self._mod.fact_checker
        session = self._mod.session
        if not fc or not session:
            return
        try:
            result = await fc.check_claim(claim)
            if result:
                event = FactCheckEvent(
                    claim=result.claim,
                    source=result.sources[0].url if result.sources else None,
                    result=result.verdict == "verified",
                    confidence=0.7 if result.verdict == "verified" else 0.3,
                    metadata={
                        "verdict": result.verdict,
                        "sources": [s.model_dump() for s in result.sources],
                        "explanation": result.explanation,
                    },
                )
                session.event_bus.publish(event)
        except Exception:
            pass

    async def _integrate(self, event: FactCheckEvent) -> None:
        session = self._mod.session
        if not session:
            return

        metadata = event.metadata or {}
        verdict = metadata.get("verdict", "unverified")
        explanation = metadata.get("explanation", "")

        emoji = _VERDICT_EMOJI.get(verdict, "⚪")
        label = _VERDICT_LABEL.get(verdict, "Unbekannt")

        summary_prompt = (
            f"Summarize this fact-check result in ONE short sentence in German. "
            f"Be very concise.\n\nCLAIM: {event.claim}\nVERDICT: {verdict}\n"
            f"EXPLANATION: {explanation}\n\nReturn ONLY the one-sentence summary, no other text."
        )

        try:
            fc_content = await self._mod._stream_llm(
                [{"role": "user", "content": summary_prompt}]
            )
            if not fc_content or len(fc_content) < 5:
                fc_content = explanation[:100] if explanation else ""
        except Exception:
            fc_content = explanation[:100] if explanation else ""

        message = self._mod._create_message(
            f"{emoji} {label}: {fc_content}",
            MessageType.FACT_CHECK,
        )
        await session.add_message(message)
