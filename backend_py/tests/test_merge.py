from __future__ import annotations

from app.conversation.canonicalize import canonicalize
from app.conversation.merge import merge_slots
from app.conversation.state import create_conversation_state


def test_merge_into_empty_state():
    state = create_conversation_state("s1")
    result = merge_slots(state, canonicalize({"category": "máy lạnh", "budget": "20 triệu"}))
    assert result.category == "air_conditioner"
    assert result.slots["budget_max"] == 20_000_000
    assert result.turn_count == 1


def test_merge_accumulates_slots_across_turns():
    state = create_conversation_state("s2")
    state = merge_slots(state, canonicalize({"category": "máy lạnh", "budget": "20 triệu"}, state.category))
    state = merge_slots(state, canonicalize({"area": "18m2"}, state.category))
    assert state.slots["budget_max"] == 20_000_000
    assert state.slots["room_area_m2"] == 18
    assert state.turn_count == 2


def test_merge_overwrites_updated_value():
    state = create_conversation_state("s3")
    state = merge_slots(state, canonicalize({"category": "máy lạnh", "budget": "20 triệu"}, state.category))
    state = merge_slots(state, canonicalize({"budget": "15 triệu"}, state.category))
    assert state.slots["budget_max"] == 15_000_000


def test_rejected_fields_accumulate_across_turns():
    state = create_conversation_state("s4")
    state = merge_slots(state, canonicalize({"category": "máy lạnh", "mau_sac_la": "đỏ"}, state.category))
    state = merge_slots(state, canonicalize({"budget": "không rõ số"}, state.category))
    assert len(state.rejected_fields) == 2


def test_slots_never_contains_duplicate_category_key():
    state = create_conversation_state("s5")
    state = merge_slots(state, canonicalize({"category": "tủ lạnh"}))
    assert "category" not in state.slots
    assert state.category == "tu_lanh"
