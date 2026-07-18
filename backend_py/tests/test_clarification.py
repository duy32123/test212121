from __future__ import annotations

from app.conversation.clarification import build_clarifying_question, choose_next_slot_to_ask, mark_slot_asked
from app.conversation.state import create_conversation_state
from app.conversation.turn import process_turn


def test_chooses_never_asked_slot_first():
    state = create_conversation_state("s1")
    missing = ["budget_max", "room_area_m2", "installation_location"]

    first = choose_next_slot_to_ask(state, missing)
    assert first.is_repeat is False
    state = mark_slot_asked(state, first.slot)

    second = choose_next_slot_to_ask(state, missing)
    assert second.slot != first.slot
    assert second.is_repeat is False


def test_mark_slot_asked_is_idempotent():
    state = create_conversation_state("s2")
    state = mark_slot_asked(state, "budget_max")
    state = mark_slot_asked(state, "budget_max")
    assert state.asked_slots == ["budget_max"]


def test_repeat_flag_when_all_missing_already_asked():
    state = create_conversation_state("s3")
    state = mark_slot_asked(state, "budget_max")
    choice = choose_next_slot_to_ask(state, ["budget_max"])
    assert choice.slot == "budget_max"
    assert choice.is_repeat is True


def test_multi_turn_never_reasks_filled_slot():
    state = create_conversation_state("s4")
    asked_questions = []

    turn = process_turn(state, {"category": "máy lạnh", "budget": "20 triệu"})
    state = turn.state
    if turn.clarifying_question:
        asked_questions.append(turn.clarifying_question.slot)
    assert turn.status == "need_clarification"
    assert "budget_max" not in asked_questions

    answer_map = {"room_area_m2": {"area": "18m2"}, "installation_location": {"location": "phòng ngủ"}}
    slot_just_asked = turn.clarifying_question.slot
    turn = process_turn(state, answer_map.get(slot_just_asked, {}))
    state = turn.state
    if turn.clarifying_question:
        asked_questions.append(turn.clarifying_question.slot)

    assert state.slots.get(slot_just_asked) is not None
    assert asked_questions.count(slot_just_asked) == 1

    remaining_slot = turn.clarifying_question.slot if turn.clarifying_question else None
    if remaining_slot:
        turn = process_turn(state, answer_map.get(remaining_slot, {}))
        state = turn.state

    assert turn.status == "ready"
    assert turn.missing_slots == []

    for slot in set(asked_questions):
        assert asked_questions.count(slot) == 1


def test_build_clarifying_question_none_when_nothing_missing():
    state = create_conversation_state("s5")
    assert build_clarifying_question(state, []) is None
