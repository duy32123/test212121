from __future__ import annotations

from app.conversation.canonicalize import canonicalize, normalize_category


def test_normalize_category_common_aliases():
    assert normalize_category("Máy lạnh") == "air_conditioner"
    assert normalize_category("điều hòa") == "air_conditioner"
    assert normalize_category("Tủ lạnh") == "tu_lanh"
    assert normalize_category("Máy giặt") == "may_giat"
    assert normalize_category("không xác định !!!") is None


def test_canonicalize_location_to_installation_location():
    result = canonicalize({"category": "máy lạnh", "location": "phòng ngủ"})
    assert result.valid_slots["installation_location"] == "phòng ngủ"
    assert "location" not in result.valid_slots
    assert result.rejected_fields == []


def test_canonicalize_parses_budget_vietnamese():
    result = canonicalize({"category": "máy lạnh", "budget": "20 triệu"})
    assert result.valid_slots["budget_max"] == 20_000_000


def test_canonicalize_parses_area():
    result = canonicalize({"category": "máy lạnh", "area": "18m2"})
    assert result.valid_slots["room_area_m2"] == 18


def test_canonicalize_household_alias_for_refrigerator():
    result = canonicalize({"category": "tủ lạnh", "household": "4"})
    assert result.valid_slots["household_size"] == 4


def test_unrecognized_field_not_silently_dropped():
    result = canonicalize({"category": "máy lạnh", "mau_sac_la": "đỏ"})
    assert "mau_sac_la" not in result.valid_slots
    assert any(r["field"] == "mau_sac_la" and r["reason"] == "unrecognized_field" for r in result.rejected_fields)


def test_invalid_value_not_silently_dropped():
    result = canonicalize({"category": "máy lạnh", "budget": "nhiều tiền lắm"})
    assert "budget_max" not in result.valid_slots
    assert any(r["field"] == "budget" and r["reason"] == "invalid_value" for r in result.rejected_fields)


def test_unrecognized_category_kept_in_rejected():
    result = canonicalize({"category": "???", "budget": "20 triệu"})
    assert result.category is None
    assert any(r["field"] == "category" and r["reason"] == "unrecognized_category" for r in result.rejected_fields)


def test_keeps_current_category_if_not_mentioned():
    result = canonicalize({"budget": "15 triệu"}, current_category="refrigerator")
    assert result.category == "refrigerator"
    assert result.valid_slots["budget_max"] == 15_000_000


def test_laptop_scenario_full_soft_preferences():
    result = canonicalize(
        {
            "category": "lap top",
            "budget_max": 15_000_000,
            "battery_priority": "high",
            "portability_priority": "high",
            "use_case": "student",
        }
    )
    assert result.category == "laptop"
    assert result.valid_slots["battery_priority"] == "high"
    assert result.valid_slots["portability_priority"] == "high"
    assert result.valid_slots["use_case"] == "student"
    assert result.rejected_fields == []


def test_pin_trau_does_not_create_numeric_battery_claim():
    """'pin trâu' chỉ là soft preference định tính — không được suy diễn
    thành dung lượng/thời lượng pin cụ thể nào."""
    result = canonicalize({"category": "laptop", "battery_priority": "pin trâu"})
    assert result.valid_slots["battery_priority"] == "high"
    assert not any(isinstance(v, (int, float)) for k, v in result.valid_slots.items() if "battery" in k)


def test_budget_slang_cu_recognized_in_canonicalize():
    result = canonicalize({"category": "laptop", "budget_max": "15 củ"})
    assert result.valid_slots["budget_max"] == 15_000_000
