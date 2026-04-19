from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    AGENT = "AGENT"
    FACT_CHECK = "FACT_CHECK"
    MODERATOR = "MODERATOR"
    SYSTEM = "SYSTEM"


class Message(BaseModel):
    id: Annotated[str, Field(description="Unique identifier for the message")]
    agent_id: Annotated[str, Field(description="ID of the agent who sent the message")]
    content: Annotated[str, Field(description="Content of the message")]
    timestamp: Annotated[
        datetime, Field(description="Timestamp when the message was sent")
    ]
    type: Annotated[MessageType, Field(description="Type of message")]

    model_config = {"use_enum_values": True}
