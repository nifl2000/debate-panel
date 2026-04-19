"""
Session cleanup module for managing expired discussion sessions.

This module provides background cleanup of inactive sessions to prevent memory leaks.
"""

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Optional

from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.orchestration.session import DiscussionSession

logger = get_logger(__name__)


class SessionCleanup:
    """
    Background task for cleaning up expired discussion sessions.

    Runs periodically to remove sessions that have been inactive beyond the TTL.
    Default TTL is 1 hour, cleanup runs every 5 minutes.
    """

    def __init__(
        self,
        session_store: Dict[str, "DiscussionSession"],
        ttl_seconds: int = 3600,
    ) -> None:
        """
        Initialize the session cleanup task.

        Args:
            session_store: Dictionary mapping session_id to DiscussionSession
            ttl_seconds: Time-to-live for sessions in seconds (default: 3600 = 1 hour)
        """
        self._session_store = session_store
        self._ttl_seconds = ttl_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def run_cleanup(self) -> int:
        """
        Check all sessions and delete expired ones.

        A session is expired when: last_activity + ttl_seconds < now

        Returns:
            Number of sessions deleted
        """
        now = datetime.now()
        ttl = timedelta(seconds=self._ttl_seconds)
        expired_sessions = []

        for session_id, session in self._session_store.items():
            last_activity = session.get_last_activity()
            if last_activity + ttl < now:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            session = self._session_store.pop(session_id, None)
            if session:
                logger.info(
                    f"Cleaned up expired session",
                    extra={"session_id": session_id, "operation": "cleanup"},
                )

        if expired_sessions:
            logger.info(
                f"Cleanup completed: {len(expired_sessions)} sessions removed",
                extra={"operation": "cleanup", "deleted_count": len(expired_sessions)},
            )

        return len(expired_sessions)

    async def start_cleanup_loop(self, interval_seconds: int = 300) -> None:
        """
        Start the background cleanup loop.

        Args:
            interval_seconds: How often to run cleanup (default: 300 = 5 minutes)
        """
        if self._running:
            logger.warning(
                "Cleanup loop already running", extra={"operation": "cleanup"}
            )
            return

        self._running = True

        async def loop():
            while self._running:
                try:
                    await self.run_cleanup()
                except Exception as e:
                    logger.error(
                        f"Error during cleanup",
                        extra={"operation": "cleanup", "error": str(e)},
                    )
                await asyncio.sleep(interval_seconds)

        self._cleanup_task = asyncio.create_task(loop())
        logger.info(
            f"Started cleanup loop with {interval_seconds}s interval",
            extra={"operation": "cleanup", "interval_seconds": interval_seconds},
        )

    def stop_cleanup_loop(self) -> None:
        """
        Stop the background cleanup loop.
        """
        if not self._running:
            return

        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

        logger.info("Stopped cleanup loop", extra={"operation": "cleanup"})
