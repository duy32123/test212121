from __future__ import annotations

from datetime import datetime, timezone

from app.conversation.canonicalize import CanonicalResult
from app.conversation.state import ConversationState


def merge_slots(prev_state: ConversationState, canonical_result: CanonicalResult) -> ConversationState:
    """
    Merge slot mới (đã validate) vào state cũ. Slot mới ghi đè slot cùng
    tên (khách sửa thông tin). rejected_fields CỘNG DỒN qua các turn —
    không bao giờ bị xoá âm thầm.
    """
    merged_slots = {**prev_state.slots, **canonical_result.valid_slots}
    merged_slots.pop("category", None)

    next_category = canonical_result.category or prev_state.category

    return prev_state.with_updates(
        category=next_category,
        slots=merged_slots,
        rejected_fields=[*prev_state.rejected_fields, *canonical_result.rejected_fields],
        turn_count=prev_state.turn_count + 1,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
