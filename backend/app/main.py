import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import _session_store
from app.agents.moderator import ModeratorAgent
from app.api.routes import discussion_router, export_router
from app.orchestration.cleanup import SessionCleanup
from app.services.session_reload import reload_sessions
from app.utils.logger import get_logger

logger = get_logger(__name__)

_cleanup: SessionCleanup | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup

    # Startup: reload sessions from disk, then start cleanup
    reloaded = reload_sessions(_session_store)

    cleanup_ttl = int(os.getenv("SESSION_TTL_SECONDS", "1800"))
    cleanup_interval = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))
    _cleanup = SessionCleanup(_session_store, ttl_seconds=cleanup_ttl)
    await _cleanup.start_cleanup_loop(interval_seconds=cleanup_interval)
    logger.info("Server started", extra={"operation": "startup"})

    yield

    # Shutdown: stop cleanup + cancel all moderator tasks
    if _cleanup:
        _cleanup.stop_cleanup_loop()

    cancelled = 0
    for session in _session_store.values():
        for agent in session.agents.values():
            if isinstance(agent, ModeratorAgent):
                agent.stop_loop()
                cancelled += 1

    logger.info(
        "Server shutdown",
        extra={
            "operation": "shutdown",
            "cancelled_tasks": cancelled,
            "active_sessions": len(_session_store),
        },
    )


app = FastAPI(title="DebatePanel API", lifespan=lifespan)

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(discussion_router)
app.include_router(export_router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}
