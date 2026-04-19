"""Session Logger - writes detailed debug logs per session."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

SESSION_LOGS_DIR = Path(__file__).parent.parent.parent / "logs" / "sessions"
SESSION_LOGS_DIR.mkdir(parents=True, exist_ok=True)


class SessionLogger:
    def __init__(self, session_id: str, topic: str):
        self.session_id = session_id
        self.topic = topic
        self.start_time = datetime.now()
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:40]
        self.log_path = SESSION_LOGS_DIR / f"{session_id[:8]}_{safe_topic}.log"
        self._entries = []

    def _write(self):
        with open(self.log_path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def log(self, component: str, event: str, details: Dict[str, Any] = None):
        entry = {
            "ts": (datetime.now() - self.start_time).total_seconds(),
            "clock": datetime.now().isoformat(),
            "component": component,
            "event": event,
        }
        if details:
            entry["details"] = details
        self._entries.append(entry)
        self._write()

    def log_error(self, component: str, error: str, details: Dict[str, Any] = None):
        self.log(component, "ERROR", {"error": error, **(details or {})})
