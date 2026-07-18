from __future__ import annotations

from app.catalog.catalog_store import get_catalog
from app.conversation.nlu_lexicon import (
    extract_soft_preferences,
    find_category_in_message,
    normalize_priority_value,
    normalize_use_case_value,
    parse_budget_phrase,
    parse_message_deterministic,
    resolve_category_value,
)


def _known():
    return set(get_catalog().keys())


def test_laptop_aliases_and_typos():
    known = _known()
    for phrase in ["lap top", "laptob", "labtop", "máy tính xách tay", "notebook", "laptop"]:
        assert resolve_category_value(phrase, known) == "laptop", phrase


def test_dishwasher_aliases_and_typos():
    known = _known()
    for phrase in ["máy rửa bát", "may rua bat", "dishwasher", "máy rửa chén", "may rua chen"]:
        assert resolve_category_value(phrase, known) == "may_rua_chen", phrase


def test_air_conditioner_aliases():
    known = _known()
    for phrase in ["máy lạnh", "điều hòa", "may lanh", "dieu hoa"]:
        assert resolve_category_value(phrase, known) == "air_conditioner", phrase


def test_does_not_conflate_similar_categories():
    """'Tủ mát' và 'Tủ lạnh' KHÔNG được gộp nhầm vào nhau."""
    known = _known()
    assert resolve_category_value("Tủ lạnh", known) == "tu_lanh"
    assert resolve_category_value("Tủ mát", known) != "tu_lanh"


def test_short_alias_does_not_match_inside_unrelated_word():
    """'ac' (alias máy lạnh) không được khớp nhầm vào giữa từ khác như 'xác định'."""
    known = _known()
    assert resolve_category_value("không xác định !!!", known) is None


def test_budget_phrase_cu_slang():
    assert parse_budget_phrase("tầm 15 củ") == 15_000_000
    assert parse_budget_phrase("15tr") == 15_000_000
    assert parse_budget_phrase("15 triệu") == 15_000_000


def test_soft_preference_extraction_does_not_invent_numbers():
    prefs = extract_soft_preferences("Cần con lap top pin trâu, mỏng nhẹ, tầm 15 củ để đi học")
    assert prefs == {"battery_priority": "high", "portability_priority": "high", "use_case": "student"}
    assert all(isinstance(v, str) and not v.isdigit() for v in prefs.values())


def test_normalize_priority_value_only_accepts_defined_levels():
    assert normalize_priority_value("pin trâu") == "high"
    assert normalize_priority_value("high") == "high"
    assert normalize_priority_value("2000mAh") is None  # không tự nhận số liệu bịa làm mức priority hợp lệ


def test_normalize_use_case_value():
    assert normalize_use_case_value("để đi học") == "student"
    assert normalize_use_case_value("chơi game") == "gaming"
    assert normalize_use_case_value("nấu ăn") is None


def test_parse_message_deterministic_full_example_from_spec():
    known = _known()
    result = parse_message_deterministic("Cần con lap top pin trâu, mỏng nhẹ, tầm 15 củ để đi học", known_categories=known)
    assert result == {
        "category": "laptop",
        "budget_max": 15_000_000,
        "battery_priority": "high",
        "portability_priority": "high",
        "use_case": "student",
    }


def test_parse_message_deterministic_dishwasher():
    known = _known()
    result = parse_message_deterministic("Tôi muốn mua máy rửa bát", known_categories=known)
    assert result == {"category": "may_rua_chen"}


def test_find_category_in_message_scans_full_sentence():
    known = _known()
    assert find_category_in_message("mình cần tìm cái laptob giá rẻ", known) == "laptop"
