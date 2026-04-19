import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

SESSIONS_DIR = Path(__file__).parent.parent.parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


class SessionWriter:
    def __init__(
        self,
        session_id: str,
        topic: str,
        personas: List[Dict[str, Any]],
        max_messages: int = 30,
    ):
        self.session_id = session_id
        self.topic = topic
        self.max_messages = max_messages
        self.message_count = 0

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:50]
        self.session_dir = SESSIONS_DIR / f"{timestamp}_{session_id[:8]}_{safe_topic}"
        self.session_dir.mkdir(exist_ok=True)

        self._messages_file = self.session_dir / "messages.jsonl"

        metadata = {
            "session_id": session_id,
            "topic": topic,
            "created_at": datetime.now().isoformat(),
            "max_messages": max_messages,
            "status": "running",
        }
        self._write_json("metadata.json", metadata)
        self._write_json("personas.json", personas)

    def append_message(self, msg: Dict[str, Any]) -> None:
        with open(self._messages_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.message_count += 1

        metadata = {
            "session_id": self.session_id,
            "topic": self.topic,
            "created_at": datetime.now().isoformat(),
            "max_messages": self.max_messages,
            "message_count": self.message_count,
            "status": "running",
        }
        self._write_json("metadata.json", metadata)

    def finalize(self, synthesis: str) -> str:
        messages = self._read_messages()

        personas = self._read_json("personas.json") or []

        metadata = {
            "session_id": self.session_id,
            "topic": self.topic,
            "created_at": datetime.now().isoformat(),
            "max_messages": self.max_messages,
            "message_count": self.message_count,
            "status": "completed",
        }
        self._write_json("metadata.json", metadata)

        self._write_json("messages.json", messages)

        with open(self.session_dir / "synthesis.md", "w", encoding="utf-8") as f:
            f.write(f"# Discussion Summary: {self.topic}\n\n{synthesis}")

        lines = [
            f"# Discussion: {self.topic}\n",
            f"**Datum:** {metadata['created_at']}\n",
        ]
        lines.append(f"**Personas:** {len(personas)}\n")
        lines.append(f"**Messages:** {self.message_count}\n\n")
        lines.append("## Panel\n\n")
        for p in personas:
            lines.append(f"- {p.get('emoji', '👤')} **{p['name']}** ({p['role']})\n")
            lines.append(f"  - Haltung: {p['stance']}\n")
        lines.append("\n---\n\n")

        for msg in messages:
            agent_name = msg.get("agentName") or msg.get("agent_id", "System")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            if ts:
                try:
                    ts = datetime.fromisoformat(ts).strftime("%H:%M:%S")
                except (ValueError, TypeError):
                    pass
            lines.append(f"### {agent_name} ({ts})\n\n{content}\n\n")

        lines.append("\n---\n\n## Summary\n\n")
        lines.append(synthesis)

        with open(self.session_dir / "discussion.md", "w", encoding="utf-8") as f:
            f.write("".join(lines))

        return str(self.session_dir)

    def _read_messages(self) -> List[Dict[str, Any]]:
        messages = []
        if self._messages_file.exists():
            with open(self._messages_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return messages

    def _write_json(self, filename: str, data: Any) -> None:
        with open(self.session_dir / filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _read_json(self, filename: str) -> Any:
        path = self.session_dir / filename
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
