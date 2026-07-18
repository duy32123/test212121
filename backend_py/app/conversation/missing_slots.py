from __future__ import annotations

from app.conversation.slot_schemas import get_slot_schema
from app.conversation.state import ConversationState


def compute_missing_slots(state: ConversationState) -> list[str]:
    if not state.category:
        return ["category"]

    schema = get_slot_schema(state.category)
    missing = []
    for slot_name in schema.required:
        if slot_name == "category":
            continue
        value = state.slots.get(slot_name)
        if value is None or value == "":
            missing.append(slot_name)
    return missing
