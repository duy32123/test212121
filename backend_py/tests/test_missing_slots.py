from __future__ import annotations

from app.conversation.canonicalize import canonicalize
from app.conversation.merge import merge_slots
from app.conversation.missing_slots import compute_missing_slots
from app.conversation.state import create_conversation_state


def test_no_category_yet():
    state = create_conversation_state("s1")
    assert compute_missing_slots(state) == ["category"]


def test_air_conditioner_missing_three_required_slots():
    state = create_conversation_state("s2")
    state = merge_slots(state, canonicalize({"category": "máy lạnh"}, state.category))
    missing = compute_missing_slots(state)
    assert set(missing) == {"budget_max", "room_area_m2", "installation_location"}


def test_missing_decreases_as_slots_filled():
    state = create_conversation_state("s3")
    state = merge_slots(state, canonicalize({"category": "máy lạnh", "budget": "20 triệu"}, state.category))
    assert set(compute_missing_slots(state)) == {"room_area_m2", "installation_location"}

    state = merge_slots(state, canonicalize({"area": "18m2"}, state.category))
    assert compute_missing_slots(state) == ["installation_location"]

    state = merge_slots(state, canonicalize({"location": "phòng ngủ"}, state.category))
    assert compute_missing_slots(state) == []


def test_refrigerator_different_required_set():
    state = create_conversation_state("s4")
    state = merge_slots(
        state, canonicalize({"category": "tủ lạnh", "budget": "15 triệu", "household": "4"}, state.category)
    )
    assert compute_missing_slots(state) == []


def test_default_category_only_needs_budget():
    state = create_conversation_state("s5")
    state = merge_slots(state, canonicalize({"category": "laptop", "budget": "5 triệu"}, state.category))
    assert compute_missing_slots(state) == []


def test_rejected_field_not_counted_as_present():
    state = create_conversation_state("s6")
    state = merge_slots(state, canonicalize({"category": "máy lạnh", "budget": "nhiều tiền lắm"}, state.category))
    assert "budget_max" in compute_missing_slots(state)


def test_dishwasher_missing_next_is_budget_not_category():
    """'tôi muốn mua máy rửa bát' -> category đã nhận diện được ngay
    (không hỏi lại category); missing slot còn lại là budget_max + câu hỏi
    đặc thù của ngành (household_size), KHÔNG bao giờ có 'category'."""
    state = create_conversation_state("s7")
    state = merge_slots(state, canonicalize({"category": "máy rửa bát"}, state.category))
    assert state.category == "may_rua_chen"
    missing = compute_missing_slots(state)
    assert "category" not in missing
    assert set(missing) == {"budget_max", "household_size"}
