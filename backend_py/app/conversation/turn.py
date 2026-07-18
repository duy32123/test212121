from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.conversation.canonicalize import canonicalize
from app.conversation.clarification import ClarifyingQuestion, build_clarifying_question, mark_slot_asked
from app.conversation.merge import merge_slots
from app.conversation.missing_slots import compute_missing_slots
from app.conversation.state import ConversationState


@dataclass(frozen=True)
class TurnResult:
    state: ConversationState
    missing_slots: list[str]
    clarifying_question: ClarifyingQuestion | None
    status: str  # "need_clarification" | "ready"


def process_turn(prev_state: ConversationState, raw_extraction: dict[str, Any] | None) -> TurnResult:
    canonical_result = canonicalize(raw_extraction, prev_state.category)
    new_state = merge_slots(prev_state, canonical_result)

    missing_slots = compute_missing_slots(new_state)
    clarifying_question = build_clarifying_question(new_state, missing_slots)

    if clarifying_question:
        new_state = mark_slot_asked(new_state, clarifying_question.slot)

    status = "need_clarification" if missing_slots else "ready"
    return TurnResult(state=new_state, missing_slots=missing_slots, clarifying_question=clarifying_question, status=status)
