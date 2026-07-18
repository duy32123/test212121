from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ConversationState:
    session_id: str
    category: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    asked_slots: list[str] = field(default_factory=list)
    rejected_fields: list[dict[str, Any]] = field(default_factory=list)
    turn_count: int = 0
    updated_at: str = ""

    def with_updates(self, **kwargs) -> "ConversationState":
        return replace(self, **kwargs)


def create_conversation_state(session_id: str) -> ConversationState:
    return ConversationState(session_id=session_id, updated_at=datetime.now(timezone.utc).isoformat())
