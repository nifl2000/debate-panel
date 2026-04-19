from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    PERSONA = "PERSONA"
    MODERATOR = "MODERATOR"
    FACT_CHECKER = "FACT_CHECKER"


class Agent(BaseModel):
    id: Annotated[str, Field(description="Unique identifier for the agent")]
    name: Annotated[str, Field(description="Display name of the agent")]
    role: Annotated[str, Field(description="Role or title of the agent")]
    background: Annotated[
        str, Field(description="Background information about the agent")
    ]
    stance: Annotated[str, Field(description="Stance or position on the topic")]
    type: Annotated[AgentType, Field(description="Type of agent")]
    emoji: Annotated[str, Field(default="", description="Emoji representing the agent")]

    model_config = {"use_enum_values": True}
