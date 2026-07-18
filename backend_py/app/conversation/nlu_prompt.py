from __future__ import annotations

import json

from app.conversation.state import ConversationState

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "description": "Category sản phẩm, vd 'laptop', 'air_conditioner', 'may_rua_chen'."},
        "budget_max": {"type": "number", "description": "Ngân sách tối đa (VND), suy từ '15 triệu'/'15tr'/'15 củ'..."},
        "budget_min": {"type": "number"},
        "room_area_m2": {"type": "number", "description": "Chỉ áp dụng cho máy lạnh."},
        "installation_location": {"type": "string", "description": "vd 'phòng ngủ', 'phòng khách'."},
        "household_size": {"type": "number"},
        "capacity_liters": {"type": "number"},
        "battery_priority": {
            "type": "string",
            "enum": ["high"],
            "description": "Soft preference — CHỈ ghi 'high' nếu khách nói 'pin trâu'/'pin lâu'. KHÔNG bịa dung lượng/thời lượng pin cụ thể.",
        },
        "portability_priority": {
            "type": "string",
            "enum": ["high"],
            "description": "Soft preference — 'high' nếu khách nói 'mỏng nhẹ'/'dễ mang'.",
        },
        "use_case": {"type": "string", "enum": ["student", "gaming", "work"], "description": "'student' nếu 'để đi học'/'sinh viên'; 'gaming' nếu 'gaming'/'chơi game'; 'work' nếu 'làm việc'/'văn phòng'."},
    },
    "additionalProperties": False,
}

_FEW_SHOT_EXAMPLES = [
    {
        "input": "Cần con lap top pin trâu, mỏng nhẹ, tầm 15 củ để đi học",
        "output": {
            "category": "laptop",
            "budget_max": 15000000,
            "battery_priority": "high",
            "portability_priority": "high",
            "use_case": "student",
        },
    },
    {
        "input": "Tôi muốn mua máy rửa bát",
        "output": {"category": "may_rua_chen"},
    },
    {
        "input": "Điều hòa cho phòng ngủ 18m2 dưới 20 triệu",
        "output": {
            "category": "air_conditioner",
            "room_area_m2": 18,
            "installation_location": "phòng ngủ",
            "budget_max": 20000000,
        },
    },
]


def build_nlu_prompt(state: ConversationState, missing_slots: list[str], user_message: str) -> tuple[str, str]:
    """
    Trả về (system, user) cho lời gọi LLM trích slot thô — LUÔN nhúng
    previous_state + missing_slots để LLM không hỏi lại slot đã có.

    Few-shot examples là `user query -> JSON chuẩn` THUẦN NLU (KHÔNG dùng
    câu trả lời bán hàng/tư vấn làm ví dụ), tránh làm lệch hướng model sang
    việc "trả lời khách" thay vì "trích xuất JSON".
    """
    previous_state_payload = {"category": state.category, "slots": state.slots}

    few_shot_text = "\n\n".join(
        f"Input: {ex['input']}\nOutput:\n{json.dumps(ex['output'], ensure_ascii=False, indent=2)}" for ex in _FEW_SHOT_EXAMPLES
    )

    system = "\n".join(
        [
            "Bạn là bộ trích xuất thông tin (NLU) cho trợ lý tư vấn sản phẩm điện máy.",
            "Nhiệm vụ DUY NHẤT: đọc tin nhắn của khách hàng và trả về một JSON object",
            "chứa các field khách hàng vừa cung cấp hoặc cập nhật — KHÔNG PHẢI câu trả lời tư vấn.",
            "",
            "QUY TẮC BẮT BUỘC:",
            "1. KHÔNG hỏi lại hoặc yêu cầu khách nhắc lại các field đã có trong previous_state.slots.",
            "2. Chỉ trích xuất field có căn cứ rõ ràng trong tin nhắn — không suy diễn, không bịa số liệu.",
            "3. Nếu khách đề cập field đã có nhưng với giá trị khác, ưu tiên cập nhật (khách đang sửa thông tin).",
            "4. Nếu tin nhắn không cung cấp thêm field nào, trả về object rỗng {}.",
            "5. TUYỆT ĐỐI KHÔNG được đặt câu hỏi ngược lại cho khách trong output — chỉ trích xuất, không hỏi.",
            "6. TUYỆT ĐỐI KHÔNG được tự tạo/bịa giá hoặc thông số kỹ thuật sản phẩm (đó là việc của module khác).",
            "7. 'pin trâu'/'pin lâu' CHỈ là tín hiệu định tính -> battery_priority='high'. KHÔNG được tự suy ra",
            "   dung lượng pin (mAh) hay thời lượng pin (giờ) cụ thể nào — không có căn cứ để bịa số đó.",
            "8. Output CHỈ là JSON object thuần theo đúng schema bên dưới (không markdown, không giải thích thêm).",
            "",
            f"JSON schema: {json.dumps(_JSON_SCHEMA, ensure_ascii=False)}",
            "",
            "Ví dụ (few-shot, chỉ để minh hoạ cách trích xuất, KHÔNG phải câu trả lời tư vấn khách hàng):",
            few_shot_text,
            "",
            f"missing_slots hiện tại (ưu tiên khai thác nếu khách nhắc tới): {json.dumps(missing_slots, ensure_ascii=False)}",
        ]
    )

    user = json.dumps(
        {"previous_state": previous_state_payload, "missing_slots": missing_slots, "customer_message": user_message},
        ensure_ascii=False,
        indent=2,
    )

    return system, user
