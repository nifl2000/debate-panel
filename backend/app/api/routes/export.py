from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_session_store
from app.models.message import MessageType
from app.orchestration.session import DiscussionSession


router = APIRouter(prefix="/api/discussion", tags=["export"])


class ExportFormat(str, Enum):
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"
    PDF = "PDF"


def _generate_text_export(session: DiscussionSession) -> str:
    """Generate plain text export of the discussion."""
    lines = []
    lines.append(f"Discussion: {session.topic}")
    lines.append(f"Session ID: {session.id}")
    lines.append(f"State: {session.state}")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("=" * 60)
    lines.append("")

    for msg in session.conversation_log:
        timestamp = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        agent_name = msg.agent_id
        # Try to get agent name from session agents
        if msg.agent_id in session.agents:
            agent_name = session.agents[msg.agent_id].name

        lines.append(f"[{timestamp}] {agent_name}:")
        lines.append(msg.content)
        lines.append("")

    return "\n".join(lines)


def _generate_markdown_export(session: DiscussionSession) -> str:
    """Generate markdown export of the discussion."""
    lines = []
    lines.append(f"# Discussion: {session.topic}")
    lines.append("")
    lines.append(f"**Session ID:** `{session.id}`")
    lines.append(f"**State:** {session.state}")
    lines.append(f"**Generated:** {datetime.now().isoformat()}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Agent roster
    lines.append("## Participants")
    lines.append("")
    for agent_id, agent in session.agents.items():
        lines.append(f"- **{agent.name}** ({agent.type})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Conversation
    lines.append("## Conversation")
    lines.append("")

    for msg in session.conversation_log:
        timestamp = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        agent_name = msg.agent_id
        if msg.agent_id in session.agents:
            agent_name = session.agents[msg.agent_id].name

        # Format based on message type
        if msg.type == MessageType.MODERATOR:
            lines.append(f"### [{timestamp}] Moderator: {agent_name}")
        elif msg.type == MessageType.FACT_CHECK:
            lines.append(f"### [{timestamp}] Fact Check: {agent_name}")
        else:
            lines.append(f"### [{timestamp}] {agent_name}")

        lines.append("")
        lines.append(msg.content)
        lines.append("")

    # Synthesis section (if discussion is completed)
    if session.state == "COMPLETED":
        lines.append("---")
        lines.append("")
        lines.append("## Synthesis")
        lines.append("")
        lines.append(
            "*Synthesis would be generated here when the discussion is stopped.*"
        )
        lines.append("")

    return "\n".join(lines)


@router.get("/{session_id}/export")
async def export_discussion(
    session_id: str,
    format: ExportFormat = Query(default=ExportFormat.TEXT),
    session_store: Dict[str, DiscussionSession] = Depends(get_session_store),
) -> StreamingResponse:
    """
    Export discussion transcript in various formats.

    Args:
        session_id: The discussion session ID
        format: Export format (TEXT, MARKDOWN, PDF)

    Returns:
        StreamingResponse with file download

    Raises:
        HTTPException: 404 if session not found, 501 if PDF requested
    """
    if session_id not in session_store:
        raise HTTPException(
            status_code=404, detail=f"Discussion session '{session_id}' not found"
        )

    if format == ExportFormat.PDF:
        raise HTTPException(status_code=501, detail="PDF export not implemented in V1")

    session = session_store[session_id]

    if format == ExportFormat.TEXT:
        content = _generate_text_export(session)
        filename = f"discussion_{session_id[:8]}.txt"
        media_type = "text/plain"
    elif format == ExportFormat.MARKDOWN:
        content = _generate_markdown_export(session)
        filename = f"discussion_{session_id[:8]}.md"
        media_type = "text/markdown"
    else:
        # Should not reach here due to enum validation
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    # Create streaming response
    buffer = BytesIO(content.encode("utf-8"))

    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
