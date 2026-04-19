"""
Integration tests for SessionCleanup class.

Tests cover:
- Expired sessions are deleted
- Active sessions are preserved
- Cleanup loop runs at correct interval
- Stop cleanup loop works
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from app.orchestration.cleanup import SessionCleanup
from app.orchestration.session import DiscussionSession
from app.orchestration.event_bus import EventBus


@pytest.fixture
def event_bus():
    """Create an EventBus instance for testing."""
    return EventBus()


@pytest.fixture
def session_store(event_bus):
    """Create a session store dict with some test sessions."""
    store = {}

    expired_session = DiscussionSession(
        topic="Expired Topic",
        event_bus=event_bus,
        session_id="expired_001",
    )
    expired_session._last_activity = datetime.now() - timedelta(hours=2)
    store["expired_001"] = expired_session

    active_session = DiscussionSession(
        topic="Active Topic",
        event_bus=event_bus,
        session_id="active_001",
    )
    store["active_001"] = active_session

    return store


class TestSessionCleanup:
    """Tests for SessionCleanup class."""

    def test_initialization(self, session_store):
        """Test that cleanup initializes with correct default values."""
        cleanup = SessionCleanup(session_store)
        assert cleanup._session_store is session_store
        assert cleanup._ttl_seconds == 3600
        assert cleanup._running is False

    def test_initialization_custom_ttl(self, session_store):
        """Test that cleanup can be initialized with custom TTL."""
        cleanup = SessionCleanup(session_store, ttl_seconds=1800)
        assert cleanup._ttl_seconds == 1800

    @pytest.mark.asyncio
    async def test_run_cleanup_deletes_expired_sessions(self, session_store):
        """Test that expired sessions are deleted."""
        cleanup = SessionCleanup(session_store, ttl_seconds=3600)

        deleted_count = await cleanup.run_cleanup()

        assert deleted_count == 1
        assert "expired_001" not in session_store
        assert "active_001" in session_store

    @pytest.mark.asyncio
    async def test_run_cleanup_preserves_active_sessions(self, session_store):
        """Test that active sessions are preserved."""
        cleanup = SessionCleanup(session_store, ttl_seconds=3600)

        await cleanup.run_cleanup()

        assert "active_001" in session_store
        assert session_store["active_001"].topic == "Active Topic"

    @pytest.mark.asyncio
    async def test_run_cleanup_with_no_expired_sessions(self, event_bus):
        """Test cleanup when no sessions are expired."""
        store = {}
        active_session = DiscussionSession(
            topic="Active Topic",
            event_bus=event_bus,
            session_id="active_001",
        )
        store["active_001"] = active_session

        cleanup = SessionCleanup(store, ttl_seconds=3600)

        deleted_count = await cleanup.run_cleanup()

        assert deleted_count == 0
        assert len(store) == 1

    @pytest.mark.asyncio
    async def test_run_cleanup_with_empty_store(self):
        """Test cleanup with empty session store."""
        cleanup = SessionCleanup({}, ttl_seconds=3600)

        deleted_count = await cleanup.run_cleanup()

        assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_loop_runs_at_interval(self, session_store):
        """Test that cleanup loop runs at correct interval."""
        cleanup = SessionCleanup(session_store, ttl_seconds=3600)

        await cleanup.start_cleanup_loop(interval_seconds=1)

        await asyncio.sleep(2.5)

        assert "expired_001" not in session_store

        cleanup.stop_cleanup_loop()

    @pytest.mark.asyncio
    async def test_stop_cleanup_loop(self, session_store):
        """Test that stop_cleanup_loop stops the loop."""
        cleanup = SessionCleanup(session_store, ttl_seconds=3600)

        await cleanup.start_cleanup_loop(interval_seconds=1)

        cleanup.stop_cleanup_loop()

        assert cleanup._running is False
        assert cleanup._cleanup_task is None

    @pytest.mark.asyncio
    async def test_cleanup_loop_does_not_delete_active_sessions(self, event_bus):
        """Test that cleanup loop preserves active sessions."""
        store = {}

        for i in range(3):
            session = DiscussionSession(
                topic=f"Active Topic {i}",
                event_bus=event_bus,
                session_id=f"active_{i:03d}",
            )
            store[f"active_{i:03d}"] = session

        cleanup = SessionCleanup(store, ttl_seconds=3600)

        await cleanup.start_cleanup_loop(interval_seconds=1)

        await asyncio.sleep(2.5)

        assert len(store) == 3

        cleanup.stop_cleanup_loop()

    @pytest.mark.asyncio
    async def test_multiple_expired_sessions_deleted(self, event_bus):
        """Test that multiple expired sessions are deleted."""
        store = {}

        for i in range(3):
            session = DiscussionSession(
                topic=f"Expired Topic {i}",
                event_bus=event_bus,
                session_id=f"expired_{i:03d}",
            )
            session._last_activity = datetime.now() - timedelta(hours=2)
            store[f"expired_{i:03d}"] = session

        cleanup = SessionCleanup(store, ttl_seconds=3600)

        deleted_count = await cleanup.run_cleanup()

        assert deleted_count == 3
        assert len(store) == 0

    @pytest.mark.asyncio
    async def test_cleanup_with_mixed_expired_and_active(self, event_bus):
        """Test cleanup with mix of expired and active sessions."""
        store = {}

        for i in range(3):
            session = DiscussionSession(
                topic=f"Expired Topic {i}",
                event_bus=event_bus,
                session_id=f"expired_{i:03d}",
            )
            session._last_activity = datetime.now() - timedelta(hours=2)
            store[f"expired_{i:03d}"] = session

        for i in range(2):
            session = DiscussionSession(
                topic=f"Active Topic {i}",
                event_bus=event_bus,
                session_id=f"active_{i:03d}",
            )
            store[f"active_{i:03d}"] = session

        cleanup = SessionCleanup(store, ttl_seconds=3600)

        deleted_count = await cleanup.run_cleanup()

        assert deleted_count == 3
        assert len(store) == 2
        assert "active_000" in store
        assert "active_001" in store
