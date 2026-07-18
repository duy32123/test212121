from __future__ import annotations

from dataclasses import dataclass

from app.conversation.state import ConversationState

_SLOT_QUESTIONS = {
    "category": "Anh/chị đang muốn tìm mua sản phẩm gì ạ?",
    "budget_max": "Anh/chị dự định chi trong khoảng ngân sách bao nhiêu ạ?",
    "room_area_m2": "Phòng lắp máy lạnh có diện tích khoảng bao nhiêu m² ạ?",
    "installation_location": "Anh/chị lắp cho phòng ngủ, phòng khách hay khu vực nào ạ?",
    "household_size": "Gia đình mình khoảng mấy người sử dụng ạ?",
    "capacity_liters": "Anh/chị cần dung tích khoảng bao nhiêu lít ạ?",
    "use_case": "Anh/chị dùng chủ yếu để làm gì ạ (đi học/làm việc hay chơi game)?",
    "battery_priority": "Anh/chị có ưu tiên pin trâu, dùng được lâu không ạ?",
    "portability_priority": "Anh/chị có cần loại gọn nhẹ, dễ mang theo không ạ?",
}

# Câu hỏi use_case riêng theo từng category — tránh dùng câu chung chung.
_USE_CASE_QUESTIONS_BY_CATEGORY: dict[str, str] = {
    "tablet": "Anh/chị dùng máy tính bảng chủ yếu để học tập, giải trí hay công việc ạ?",
    "desktop_pc": "Anh/chị dùng máy tính bàn chủ yếu cho văn phòng, đồ hoạ hay chơi game ạ?",
    "monitor": "Anh/chị dùng màn hình chủ yếu cho văn phòng, thiết kế hay chơi game ạ?",
    "printer": "Anh/chị dùng máy in chủ yếu cho gia đình, văn phòng nhỏ hay in khối lượng lớn ạ?",
    "smartwatch": "Anh/chị dùng đồng hồ thông minh chủ yếu để theo dõi sức khoẻ, thể thao hay thông báo ạ?",
    "phone_mic": "Anh/chị dùng micro chủ yếu để thu âm, livestream hay gọi video ạ?",
}


def _question_for_slot(slot_name: str, category: str | None = None) -> str:
    """Trả về câu hỏi cho slot, ưu tiên câu hỏi đặc thù theo category nếu có."""
    if slot_name == "use_case" and category and category in _USE_CASE_QUESTIONS_BY_CATEGORY:
        return _USE_CASE_QUESTIONS_BY_CATEGORY[category]
    return _SLOT_QUESTIONS.get(slot_name, f'Anh/chị cho em xin thêm thông tin về "{slot_name}" được không ạ?')


@dataclass(frozen=True)
class SlotChoice:
    slot: str
    is_repeat: bool


def choose_next_slot_to_ask(state: ConversationState, missing_slots: list[str]) -> SlotChoice | None:
    if not missing_slots:
        return None
    not_yet_asked = [s for s in missing_slots if s not in state.asked_slots]
    if not_yet_asked:
        return SlotChoice(slot=not_yet_asked[0], is_repeat=False)
    return SlotChoice(slot=missing_slots[0], is_repeat=True)


def mark_slot_asked(state: ConversationState, slot_name: str) -> ConversationState:
    if slot_name in state.asked_slots:
        return state
    return state.with_updates(asked_slots=[*state.asked_slots, slot_name])


@dataclass(frozen=True)
class ClarifyingQuestion:
    slot: str
    question: str
    is_repeat: bool


def build_clarifying_question(state: ConversationState, missing_slots: list[str]) -> ClarifyingQuestion | None:
    choice = choose_next_slot_to_ask(state, missing_slots)
    if not choice:
        return None
    return ClarifyingQuestion(
        slot=choice.slot,
        question=_question_for_slot(choice.slot, category=state.category),
        is_repeat=choice.is_repeat,
    )

