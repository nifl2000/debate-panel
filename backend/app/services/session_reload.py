"""Reload sessions from disk on server startup."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict

from app.models.discussion import DiscussionConfig, DiscussionState
from app.models.message import Message, MessageType
from app.orchestration.event_bus import EventBus
from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.orchestration.session import DiscussionSession

logger = get_logger(__name__)

SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"


def reload_sessions(session_store: Dict[str, "DiscussionSession"]) -> int:
    if not SESSIONS_DIR.exists():
        return 0

    restored = 0
    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        if not session_dir.is_dir():
            continue

        metadata_file = session_dir / "metadata.json"
        if not metadata_file.exists():
            continue

        try:
            with open(metadata_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            session_id = meta.get("session_id")
            topic = meta.get("topic", "Unknown")
            max_messages = meta.get("max_messages", 30)
            status = meta.get("status", "running")

            if not session_id or session_id in session_store:
                continue

            event_bus = EventBus()
            config = DiscussionConfig(max_messages=max_messages)

            from app.orchestration.session import DiscussionSession

            session = DiscussionSession(topic=topic, event_bus=event_bus, config=config)
            session.id = session_id

            messages_file = session_dir / "messages.jsonl"
            if messages_file.exists():
                with open(messages_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            msg = Message(
                                id=data.get("id", ""),
                                agent_id=data.get("agent_id", ""),
                                content=data.get("content", ""),
                                timestamp=data.get("timestamp", ""),
                                type=MessageType(data.get("type", "AGENT")),
                            )
                            session.conversation_log.append(msg)
                        except (json.JSONDecodeError, ValueError):
                            pass

            if status == "completed":
                session.state = DiscussionState.COMPLETED
                session.phase = "COMPLETED"

                synthesis_file = session_dir / "synthesis.md"
                if synthesis_file.exists():
                    with open(synthesis_file, "r", encoding="utf-8") as f:
                        session.synthesis = f.read()

            session_store[session_id] = session
            restored += 1
            logger.info(
                "Restored session from disk",
                extra={
                    "session_id": session_id,
                    "topic": topic,
                    "status": status,
                    "message_count": len(session.conversation_log),
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to restore session from {session_dir.name}: {e}",
                extra={"operation": "reload_session", "error": str(e)},
            )

    if restored:
        logger.info(
            f"Restored {restored} sessions from disk",
            extra={"operation": "reload_sessions", "restored_count": restored},
        )

    return restored
