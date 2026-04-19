from dataclasses import dataclass, field


@dataclass
class ModeratorContext:
    messages_since_moderator: int = 0
    moderator_cooldown: int = 0
    loop_iteration: int = 0
    current_phase: str = "INTRODUCTION"
