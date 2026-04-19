from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class DiscussionState(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class DiscussionConfig(BaseModel):
    max_messages: int = Field(default=20, ge=1, le=100)
    language: str = Field(default="auto")
    model: str = Field(default="qwen3.6-plus")
    fact_check_enabled: bool = Field(default=False)
    consensus_mode: bool = Field(default=False)


class DiscussionSession(BaseModel):
    id: Annotated[str, Field(description="Unique identifier for the discussion")]
    topic: Annotated[str, Field(description="Topic or question being discussed")]
    state: Annotated[
        DiscussionState, Field(description="Current state of the discussion")
    ]
    conversation_log: Annotated[
        list,
        Field(default_factory=list, description="List of messages in the discussion"),
    ]
    agents: Annotated[
        list,
        Field(
            default_factory=list,
            description="List of agents participating in the discussion",
        ),
    ]
    config: Annotated[DiscussionConfig, Field(description="Discussion configuration")]

    model_config = {"use_enum_values": True}
