import asyncio
import json
from datetime import datetime
from typing import Dict, List, TYPE_CHECKING, AsyncGenerator
import random

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.moderator import ModeratorAgent
from app.agents.persona import PersonaAgent
from app.agents.fact_checker import FactCheckerAgent
from app.llm.client import LLMClient
from app.models.agent import Agent
from app.models.discussion import DiscussionConfig
from app.orchestration.session import DiscussionSession
from app.orchestration.event_bus import EventBus, BaseEvent
from app.services.panel_generator import PanelGenerator
from app.api.dependencies import get_session_store, get_llm_client, rate_limit_check
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/discussion", tags=["discussion"])

MODERATOR_NAMES = [
    "Clara Vogel",
    "Anna Bergmann",
    "Sophie Richter",
    "Lena Hartmann",
    "Marie Schneider",
    "Julia Weber",
    "Sarah Fischer",
    "Laura Müller",
    "Katharina Braun",
    "Elena Schmidt",
    "Petra Wagner",
    "Sabine Becker",
    "Monika Schulz",
    "Birgit Hoffmann",
    "Claudia Schäfer",
]


class StartDiscussionRequest(BaseModel):
    topic: str
    max_messages: int = 30
    model: str = "qwen3-coder-next"
    fact_check_enabled: bool = False
    consensus_mode: bool = False
    provider: str = "alibaba"


class StartDiscussionBody(BaseModel):
    max_messages: int = 30


class DiscussionResponse(BaseModel):
    topic: str
    state: str
    messages: List[dict]
    agents: List[Agent]


class PauseResponse(BaseModel):
    session_id: str
    state: str
    message: str


class StopResponse(BaseModel):
    session_id: str
    state: str
    synthesis: str


class SSEEvent(BaseModel):
    event: str
    data: dict


class PersonaUpdateRequest(BaseModel):
    name: str
    role: str
    background: str
    stance: str
    emoji: str = ""


class InjectRequest(BaseModel):
    instruction: str


class InjectResponse(BaseModel):
    status: str
    message: str


class PersonaAddRequest(BaseModel):
    name: str
    role: str
    background: str
    stance: str
    emoji: str = ""


class StartDiscussionResponse(BaseModel):
    session_id: str
    personas: List[Agent]
    status: str = "generating"


class StatusResponse(BaseModel):
    session_id: str
    status: str
    message: str
    personas: List[Agent] = []
    moderator_name: str = ""


@router.post("/start", response_model=StartDiscussionResponse)
async def start_discussion(
    request: Request,
    body: StartDiscussionRequest,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> StartDiscussionResponse:
    await rate_limit_check(request)

    llm_client = LLMClient(model=body.model)

    event_bus = EventBus()
    config = DiscussionConfig(
        max_messages=body.max_messages,
        fact_check_enabled=body.fact_check_enabled,
        consensus_mode=body.consensus_mode,
    )

    session = DiscussionSession(
        topic=body.topic,
        event_bus=event_bus,
        config=config,
    )

    session.logger.log(
        "api",
        "start_discussion",
        {
            "topic": body.topic,
            "model": body.model,
            "max_messages": body.max_messages,
        },
    )
    session.generation_status = "starting"
    session.generation_message = "Starting discussion..."

    session_store[session.id] = session

    async def generate_panel_async():
        try:
            session.generation_status = "detecting_language"
            session.generation_message = "Detecting language..."
            await asyncio.sleep(0.5)

            session.generation_status = "generating_panel"
            session.generation_message = "Generating panel..."
            panel_generator = PanelGenerator(llm_client)
            personas = await panel_generator.generate_panel(
                topic=body.topic,
                session=session,
            )

            session._generation_status = "creating_personas"
            personas_data = []
            for i, persona in enumerate(personas):
                session.add_agent(persona)
                personas_data.append(
                    {
                        "id": persona.id,
                        "name": persona.name,
                        "role": persona.role,
                        "background": persona.background,
                        "stance": persona._stance,
                        "emoji": persona.emoji,
                        "type": "PERSONA",
                    }
                )
                session.generation_message = (
                    f"Persona {i + 1}/{len(personas)}: {persona.name}"
                )
                await asyncio.sleep(0.3)

            session.init_session_writer(personas_data)

            session.generation_status = "ready"
            session.generation_message = f"{len(personas)} personas ready!"
            session.personas = personas
        except Exception as e:
            session.generation_status = "error"
            session.generation_message = f"Error: {str(e)}"

    task = asyncio.create_task(generate_panel_async())
    task.add_done_callback(
        lambda t: (
            logger.error(f"Panel generation failed: {t.exception()}", exc_info=True)
            if t.exception()
            else None
        )
    )
    session._generation_task = task

    return StartDiscussionResponse(
        session_id=session.id,
        personas=[],
        status="generating",
    )


@router.get("/{session_id}/status", response_model=StatusResponse)
async def get_generation_status(
    session_id: str,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> StatusResponse:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    status = session.generation_status
    message = session.generation_message
    personas = session.personas

    persona_models: List[Agent] = []
    for p in personas:
        if isinstance(p, PersonaAgent):
            persona_models.append(p.to_agent_model())

    return StatusResponse(
        session_id=session_id,
        status=status,
        message=message,
        personas=persona_models,
        moderator_name=getattr(session, "moderator_name", ""),
    )


@router.put("/{session_id}/personas/{persona_id}")
async def update_persona(
    session_id: str,
    persona_id: str,
    body: PersonaUpdateRequest,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> dict:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    agent = session.agents.get(persona_id)

    if not agent or not isinstance(agent, PersonaAgent):
        raise HTTPException(status_code=404, detail="Persona not found")

    agent.name = body.name
    agent.role = body.role
    agent.background = body.background
    agent.stance = body.stance
    if body.emoji:
        agent.emoji = body.emoji

    session.logger.log(
        "api",
        "persona_updated",
        {
            "persona_id": persona_id,
            "name": body.name,
        },
    )

    return {"status": "updated", "persona_id": persona_id}


@router.delete("/{session_id}/personas/{persona_id}")
async def delete_persona(
    session_id: str,
    persona_id: str,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> dict:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    agent = session.agents.get(persona_id)

    if not agent or not isinstance(agent, PersonaAgent):
        raise HTTPException(status_code=404, detail="Persona not found")

    personas = session.personas
    session.personas = [p for p in personas if p.id != persona_id]

    del session.agents[persona_id]

    session.logger.log(
        "api",
        "persona_deleted",
        {
            "persona_id": persona_id,
            "remaining_count": len(session.agents) - 1,
        },
    )

    return {"status": "deleted", "persona_id": persona_id}


@router.post("/{session_id}/personas")
async def add_persona(
    session_id: str,
    body: PersonaAddRequest,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
    llm_client: LLMClient = Depends(get_llm_client),
) -> dict:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    agent_id = f"persona_{session.id[:4]}_{len(session.agents):04x}"

    persona = PersonaAgent(
        id=agent_id,
        name=body.name,
        role=body.role,
        background=body.background,
        stance=body.stance,
        llm_client=llm_client,
        session=session,
        emoji=body.emoji,
    )

    session.agents[agent_id] = persona

    personas = session.personas
    personas.append(persona)
    session.personas = personas

    session.logger.log(
        "api",
        "persona_added",
        {
            "persona_id": agent_id,
            "name": body.name,
            "total_count": len(personas),
        },
    )

    return {"status": "added", "persona_id": agent_id}


@router.post("/{session_id}/start-discussion")
async def start_discussion_flow(
    session_id: str,
    request: Request,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
    llm_client: LLMClient = Depends(get_llm_client),
) -> dict:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    personas = session.personas

    if not personas:
        raise HTTPException(status_code=400, detail="Panel not ready")

    try:
        body = await request.json()
        requested_max = body.get("max_messages")
        if requested_max is not None:
            session.config.max_messages = requested_max
    except Exception:
        pass

    session.logger.log("api", "start_discussion_flow", {
        "persona_count": len(personas),
        "max_messages": session.config.max_messages,
    })
    session.start_discussion()

    moderator_name = random.choice(MODERATOR_NAMES)
    session.moderator_name = moderator_name

    fact_checker = FactCheckerAgent(
        llm_client=llm_client,
        session=session,
    )

    moderator = ModeratorAgent(
        id=f"moderator_{session.id[:8]}",
        name=moderator_name,
        llm_client=llm_client,
        session=session,
        emoji="🎙️",
        fact_checker=fact_checker,
    )
    session.add_agent(moderator)
    moderator.start_loop()

    return {"status": "discussion_started", "moderator_name": moderator_name}


@router.post("/{session_id}/inject", response_model=InjectResponse)
async def inject_instruction(
    session_id: str,
    body: InjectRequest,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> InjectResponse:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    await session.inject_instruction(body.instruction)

    session.logger.log(
        "api", "instruction_injected", {"instruction": body.instruction[:100]}
    )

    return InjectResponse(
        status="injected",
        message=f"Anweisung injiziert: {body.instruction[:50]}...",
    )


@router.get("/{session_id}", response_model=DiscussionResponse)
async def get_discussion(
    session_id: str,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> DiscussionResponse:
    if session_id not in session_store:
        raise HTTPException(
            status_code=404, detail=f"Discussion session '{session_id}' not found"
        )

    session = session_store[session_id]

    messages = [
        {
            "id": msg.id,
            "agent_id": msg.agent_id,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat(),
            "type": msg.type,
        }
        for msg in session.conversation_log
    ]

    agents: List[Agent] = []
    for agent in session.agents.values():
        if isinstance(agent, PersonaAgent):
            agents.append(agent.to_agent_model())
        else:
            from app.models.agent import Agent as AgentModel

            agents.append(
                AgentModel(
                    id=agent.id,
                    name=agent.name,
                    role="",
                    background="",
                    stance="",
                    type=agent.type,
                )
            )

    return DiscussionResponse(
        topic=session.topic,
        state=session.state,
        messages=messages,
        agents=agents,
    )


@router.post("/{session_id}/pause", response_model=PauseResponse)
async def pause_discussion(
    session_id: str,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> PauseResponse:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]

    if session.state.value == "COMPLETED":
        raise HTTPException(status_code=400, detail="Discussion already completed")

    session.pause_discussion()

    for agent in session.agents.values():
        if isinstance(agent, ModeratorAgent):
            agent.stop_loop()

    return PauseResponse(
        session_id=session_id,
        state="PAUSED",
        message="Discussion paused",
    )


@router.post("/{session_id}/resume", response_model=PauseResponse)
async def resume_discussion(
    session_id: str,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
    llm_client: LLMClient = Depends(get_llm_client),
) -> PauseResponse:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    session.resume_discussion()

    moderator = None
    for agent in session.agents.values():
        if isinstance(agent, ModeratorAgent):
            moderator = agent
            break

    if moderator:
        moderator.resume_loop()

    return PauseResponse(
        session_id=session_id,
        state="ACTIVE",
        message="Discussion resumed",
    )


@router.post("/{session_id}/stop", response_model=StopResponse)
async def stop_discussion(
    session_id: str,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> StopResponse:
    if session_id not in session_store:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_store[session_id]
    session.logger.log("api", "stop_discussion")
    session.stop_discussion()

    moderator = None
    for agent in session.agents.values():
        if isinstance(agent, ModeratorAgent):
            moderator = agent
            break

    synthesis = "Discussion stopped."

    if moderator:
        moderator.stop_loop()
        try:
            synthesis_msg = await moderator.generate_synthesis()
            synthesis = synthesis_msg.content
            session.logger.log("api", "synthesis_generated", {"length": len(synthesis)})
        except Exception as e:
            session.logger.log_error("api", f"Synthesis failed: {e}")
            synthesis = "Discussion stopped. Synthesis generation failed."

    session_dir = session.finalize_session(synthesis)
    session.logger.log("api", "session_finalized", {"session_dir": session_dir})

    return StopResponse(
        session_id=session_id,
        state="COMPLETED",
        synthesis=synthesis,
    )


@router.get("/{session_id}/stream")
async def stream_discussion(
    request: Request,
    session_id: str,
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> StreamingResponse:
    if session_id not in session_store:
        raise HTTPException(
            status_code=404, detail=f"Discussion session '{session_id}' not found"
        )

    session = session_store[session_id]
    event_queue: asyncio.Queue = asyncio.Queue()
    handlers: list = []

    def make_handler(event_type: str):
        def handler(event) -> None:
            try:
                event_queue.put_nowait((event_type, event))
            except asyncio.QueueFull:
                pass

        return handler

    for event_type in [
        "agent_message",
        "fact_check",
        "moderator_command",
        "stall_detected",
    ]:
        h = make_handler(event_type)
        handlers.append((event_type, h))
        session.event_bus.subscribe(event_type, h)

    def format_event(event_type: str, event) -> str:
        meta = getattr(event, "metadata", {}) or {}
        raw_type = meta.get("agent_type", event_type.upper())
        if raw_type == "AGENT_MESSAGE":
            agent_type = "AGENT"
        elif raw_type == "MODERATOR_COMMAND":
            agent_type = "MODERATOR"
        else:
            agent_type = raw_type
        data = {
            "type": agent_type,
            "agent_id": getattr(event, "agent_id", "system"),
            "agent_type": agent_type,
            "content": getattr(event, "content", getattr(event, "claim", "")),
            "metadata": {
                "message_id": meta.get("message_id", f"evt_{id(event)}"),
                "timestamp": meta.get("timestamp", datetime.now().isoformat()),
                "persona_name": meta.get("persona_name", event_type),
                **(
                    {"source_url": event.source}
                    if hasattr(event, "source") and event.source
                    else {}
                ),
                **({"sources": meta.get("sources", [])} if meta.get("sources") else {}),
            },
        }
        return f"data: {json.dumps(data)}\n\n"

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            for msg in session.conversation_log:
                persona = session.agents.get(msg.agent_id)
                agent_name = persona.name if hasattr(persona, "name") else msg.agent_id
                msg_type = msg.type.value if hasattr(msg.type, "value") else msg.type
                event_data = {
                    "type": msg_type,
                    "agent_id": msg.agent_id,
                    "agent_type": msg_type,
                    "content": msg.content,
                    "metadata": {
                        "message_id": msg.id,
                        "timestamp": msg.timestamp.isoformat(),
                        "persona_name": agent_name,
                    },
                }
                yield f"data: {json.dumps(event_data)}\n\n"

            while True:
                try:
                    event_type, event = await asyncio.wait_for(
                        event_queue.get(), timeout=15.0
                    )
                    yield format_event(event_type, event)
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                if await request.is_disconnected():
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
        finally:
            for event_type, h in handlers:
                session.event_bus.unsubscribe(event_type, h)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
