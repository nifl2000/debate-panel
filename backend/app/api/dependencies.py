import os
from typing import Dict
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()
from app.llm.client import LLMClient
from app.orchestration.session import DiscussionSession
from app.services.panel_generator import PanelGenerator


_session_store: Dict[str, DiscussionSession] = {}
_rate_limit_store: Dict[str, Dict[float, int]] = {}


def get_session_store() -> Dict[str, DiscussionSession]:
    return _session_store


def get_llm_client() -> LLMClient:
    """Get LLM client instance, reading provider and model from environment variables.

    Environment variables:
        LLM_PROVIDER: The LLM provider to use (default: "alibaba")
        LLM_MODEL: The model to use (default: "")
    """
    try:
        provider = os.getenv("LLM_PROVIDER", "alibaba")
        model = os.getenv("LLM_MODEL", "")
        return LLMClient(provider=provider, model=model)
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"LLM service unavailable: {str(e)}"
        )


def get_panel_generator(llm_client: LLMClient) -> PanelGenerator:
    return PanelGenerator(llm_client)


async def get_session(
    session_id: str,
    session_store: Dict[str, DiscussionSession],
) -> DiscussionSession:
    if session_id not in session_store:
        raise HTTPException(
            status_code=404, detail=f"Discussion session '{session_id}' not found"
        )
    return session_store[session_id]


async def rate_limit_check(
    request: Request,
    max_requests: int = 100,
    window_seconds: int = 60,
) -> None:
    import time

    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()

    if client_ip in _rate_limit_store:
        _rate_limit_store[client_ip] = {
            ts: count
            for ts, count in _rate_limit_store[client_ip].items()
            if current_time - ts < window_seconds
        }
    else:
        _rate_limit_store[client_ip] = {}

    total_requests = sum(_rate_limit_store[client_ip].values())

    if total_requests >= max_requests:
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Please try again later."
        )

    _rate_limit_store[client_ip][current_time] = (
        _rate_limit_store[client_ip].get(current_time, 0) + 1
    )
