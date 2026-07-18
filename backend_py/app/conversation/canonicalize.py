"""
conversation/canonicalize.py — port trực tiếp từ backend Node (M1).

Category resolution + budget phrase + soft preference giờ tập trung trong
`nlu_lexicon.py` (xem module đó để biết chi tiết nguyên tắc fuzzy-match/
không bịa category). File này chỉ còn giữ phần bookkeeping đặc thù của
canonicalize (merge slot, rejected_fields, validator theo từng slot).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.conversation import nlu_lexicon
from app.conversation.slot_schemas import get_slot_schema


def normalize_category(raw: Any) -> str | None:
    """Giữ lại wrapper này để không phải sửa mọi nơi đang import
    `normalize_category` từ module này — logic thật nằm ở nlu_lexicon."""
    from app.catalog.catalog_store import get_catalog

    try:
        known_categories = get_catalog().keys()
    except Exception:  # noqa: BLE001 — catalog chưa sẵn sàng (vd test cô lập không cần catalog thật)
        known_categories = None

    return nlu_lexicon.resolve_category_value(raw, known_categories=known_categories)


# --- Alias field thô -> slot canonical (dùng chung mọi category vì tên
#     slot đã được chuẩn hoá thống nhất trong slot_schemas.py) ---
_FIELD_ALIASES = {
    "location": "installation_location",
    "vị trí lắp": "installation_location",
    "noi_lap_dat": "installation_location",
    "nơi lắp đặt": "installation_location",
    "area": "room_area_m2",
    "dien_tich": "room_area_m2",
    "diện tích": "room_area_m2",
    "budget": "budget_max",
    "ngan_sach": "budget_max",
    "ngân sách": "budget_max",
    "max_budget": "budget_max",
    "min_budget": "budget_min",
    "household": "household_size",
    "số người": "household_size",
    "so_nguoi": "household_size",
    "family_size": "household_size",
    "capacity": "capacity_liters",
    "dung_tich": "capacity_liters",
    "dung tích": "capacity_liters",
    "quiet": "noise_priority",
    "ưu tiên êm": "noise_priority",
    "save_power": "power_saving_priority",
    "tiết kiệm điện": "power_saving_priority",
    "sunny": "sun_exposure",
    "có nắng": "sun_exposure",
    "nắng trực tiếp": "sun_exposure",
    "battery": "battery_priority",
    "pin": "battery_priority",
    "portability": "portability_priority",
    "gọn nhẹ": "portability_priority",
    "usecase": "use_case",
}


def _to_number_vnd(raw) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    parsed = nlu_lexicon.parse_budget_phrase(raw)
    return float(parsed) if parsed is not None else None


def _to_area_m2(raw) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    s = raw.lower().replace(" ", "")
    m = re.match(r"^(\d+(?:[.,]\d+)?)(m2|m²)?$", s)
    return float(m.group(1).replace(",", ".")) if m else None


def _to_household_or_capacity(raw) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", raw)
    return float(m.group(1).replace(",", ".")) if m else None


def _to_spec_number(raw) -> float | None:
    """Parse spec slot dạng dung tích/khối lượng/số bộ thành float.
    '100 lít' / '8 kg' / '9 bộ' / 8 -> số tương ứng."""
    return _to_household_or_capacity(raw)


def _to_bool_vn(true_words: tuple[str, ...]):
    def parser(raw) -> bool | None:
        if isinstance(raw, bool):
            return raw
        if not isinstance(raw, str):
            return None
        s = raw.strip().lower()
        if s in true_words or s in ("có", "co", "yes", "true"):
            return True
        if s in ("không", "khong", "no", "false"):
            return False
        return None

    return parser


def _to_nonempty_string(raw) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


_VALIDATORS = {
    "category": _to_nonempty_string,
    "budget_max": _to_number_vnd,
    "budget_min": _to_number_vnd,
    "room_area_m2": _to_area_m2,
    "household_size": _to_household_or_capacity,
    # Spec-derived capacity slots — dùng chung parser số từ chuỗi
    "capacity_liters": _to_spec_number,
    "wash_capacity_kg": _to_spec_number,
    "dry_capacity_kg": _to_spec_number,
    "capacity_sets": _to_spec_number,
    "tank_liters": _to_spec_number,
    "installation_location": _to_nonempty_string,
    "noise_priority": _to_bool_vn(("ưu tiên êm",)),
    "power_saving_priority": _to_bool_vn(()),
    "sun_exposure": _to_bool_vn(("nhiều nắng", "bị nắng")),
    # Soft preference — CHỈ chuẩn hoá về mức định tính ("high") hoặc enum
    # use_case ("student"/"gaming"); KHÔNG BAO GIỜ suy diễn thành số liệu cụ
    # thể (vd dung lượng pin/thời lượng pin từ "pin trâu").
    "battery_priority": nlu_lexicon.normalize_priority_value,
    "portability_priority": nlu_lexicon.normalize_priority_value,
    "use_case": nlu_lexicon.normalize_use_case_value,
    # brand: field CÓ THẬT trong dữ liệu sản phẩm (product["brand"]) — chỉ
    # cần chuỗi không rỗng, retrieval sẽ tự khớp lại với brand thật trong
    # catalog (xem filter_products.py), không suy diễn gì thêm ở đây.
    "brand": _to_nonempty_string,
}


@dataclass
class CanonicalResult:
    category: str | None
    valid_slots: dict[str, Any] = field(default_factory=dict)
    rejected_fields: list[dict[str, Any]] = field(default_factory=list)


def canonicalize(raw_extraction: dict[str, Any] | None, current_category: str | None = None) -> CanonicalResult:
    """
    Chuẩn hoá field/giá trị thô từ NLU. KHÔNG âm thầm bỏ field — field
    không nhận diện được hoặc giá trị không hợp lệ đều trả về trong
    rejected_fields kèm lý do.
    """
    rejected: list[dict[str, Any]] = []
    valid: dict[str, Any] = {}

    if not raw_extraction:
        return CanonicalResult(category=current_category, valid_slots=valid, rejected_fields=rejected)

    category = current_category
    if "category" in raw_extraction:
        normalized = normalize_category(raw_extraction["category"])
        if normalized:
            category = normalized
        else:
            rejected.append({"field": "category", "reason": "unrecognized_category", "raw_value": raw_extraction["category"]})

    schema = get_slot_schema(category)
    known_slots = set(schema.required) | set(schema.optional)

    for raw_key, raw_value in raw_extraction.items():
        if raw_key == "category":
            continue
        canonical_key = _FIELD_ALIASES.get(raw_key, raw_key if raw_key in known_slots else None)
        if not canonical_key:
            rejected.append({"field": raw_key, "reason": "unrecognized_field", "raw_value": raw_value})
            continue

        validator = _VALIDATORS.get(canonical_key)
        validated_value = validator(raw_value) if validator else raw_value

        if validated_value is None or validated_value == "":
            rejected.append({"field": raw_key, "reason": "invalid_value", "raw_value": raw_value})
            continue

        valid[canonical_key] = validated_value

    if category:
        valid["category"] = category

    return CanonicalResult(category=category, valid_slots=valid, rejected_fields=rejected)
