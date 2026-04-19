from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.agents.moderator import ModeratorAgent


class SpeakerSelector:
    def __init__(self, moderator: "ModeratorAgent") -> None:
        self._mod = moderator

    def select(self, personas: list) -> Optional[Any]:
        if not personas:
            return None

        session = self._mod.session
        if not session:
            return None

        history = session.get_speaker_history(last_n=10)
        recent_speakers = set(history[-4:]) if len(history) >= 4 else set()

        candidates = [p for p in personas if p.id not in recent_speakers]
        if not candidates:
            candidates = personas

        last_messages = session.conversation_log[-6:]
        last_content = " ".join(m.content.lower() for m in last_messages)

        scores = []
        for persona in candidates:
            score = 1.0
            name_mentions = last_content.count(persona.name.lower().split()[-1].lower())
            score += name_mentions * 0.5
            speak_count = history.count(persona.id)
            score -= speak_count * 0.2
            scores.append((score, persona))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores[0][1] if scores else None
