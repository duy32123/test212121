from __future__ import annotations

from app.retrieval.filter_products import filter_products


def ac(id_, price, area_min=None, area_max=None):
    return {
        "product_id": id_,
        "category": "air_conditioner",
        "effective_price": price,
        "spec": {"area_min_m2": area_min, "area_max_m2": area_max},
    }


def fridge(id_, price, household_text=None):
    return {
        "product_id": id_,
        "category": "refrigerator",
        "effective_price": price,
        "spec": {"so_nguoi_su_dung": household_text},
    }


def pc(id_, price):
    return {"product_id": id_, "category": "desktop_pc", "effective_price": price, "spec": {}}


def test_strict_match_on_budget_and_area():
    products = [
        ac("AC-1", 12_000_000, 15, 20),
        ac("AC-2", 18_000_000, 20, 30),
        ac("AC-3", 25_000_000, 15, 20),
        ac("AC-4", 10_000_000, 30, 40),
        ac("AC-5", 9_000_000, None, None),
    ]
    result = filter_products("air_conditioner", {"budget_max": 20_000_000, "room_area_m2": 18}, products)
    assert result.status == "ok"
    assert result.relaxed_steps == []
    assert [p["product_id"] for p in result.products] == ["AC-1"]


def test_relaxes_area_constraint_when_no_strict_match():
    products = [
        ac("AC-4", 10_000_000, 30, 40),
        ac("AC-5", 9_000_000, None, None),
    ]
    result = filter_products("air_conditioner", {"budget_max": 11_000_000, "room_area_m2": 18}, products)
    assert result.status == "relaxed"
    assert result.relaxed_steps == ["dropped_room_area_m2_constraint"]
    ids = [p["product_id"] for p in result.products]
    assert "AC-4" in ids and "AC-5" in ids


def test_relaxes_budget_after_area_when_still_empty():
    products = [ac("AC-5", 9_000_000, None, None)]
    result = filter_products("air_conditioner", {"budget_max": 8_500_000, "room_area_m2": 18}, products)
    assert result.status == "relaxed"
    assert result.relaxed_steps == ["dropped_room_area_m2_constraint", "increased_budget_15pct"]


def test_no_results_after_exhausting_relax_steps():
    products = [ac("AC-1", 12_000_000, 15, 20)]
    result = filter_products("air_conditioner", {"budget_max": 1_000_000, "room_area_m2": 18}, products)
    assert result.status == "no_results"
    assert result.products == []
    assert "chưa" in result.message.lower() or "không" in result.message.lower()


def test_product_without_price_always_excluded():
    products = [ac("AC-NOPRICE", None, 15, 20)]
    result = filter_products("air_conditioner", {"budget_max": 100_000_000, "room_area_m2": 18}, products)
    assert result.status == "no_results"


def test_category_without_spec_map_falls_back_to_budget_only():
    """Kể từ khi chuyển sang nguồn DMX, 'tu_lanh' (Tủ lạnh) CHƯA có spec_map
    trong dmx_registry.json -> chỉ lọc theo ngân sách, không có range slot."""
    products = [fridge("FR-1", 15_000_000, "3 - 4 người"), fridge("FR-2", 22_000_000, "4 - 5 người")]
    result = filter_products("tu_lanh", {"budget_max": 16_000_000, "household_size": 4}, products)
    assert result.status == "ok"
    # household_size không được dùng để lọc (không có range_slots cho category này)
    assert [p["product_id"] for p in result.products] == ["FR-1"]


def test_text_range_kind_mechanism_still_works_when_wired(monkeypatch):
    """Cơ chế RangeSlotConfig(kind='text_range') vẫn hoạt động đúng — kiểm
    tra bằng cách tạm đăng ký 1 category giả có range slot kiểu này, để
    không mất test coverage cho cơ chế (dù hiện tại chưa category DMX nào
    dùng tới do dmx_registry.json mới chỉ có spec_map cho air_conditioner)."""
    from app.conversation import slot_schemas

    fake_schema = slot_schemas.SlotSchema(
        required=["category", "budget_max", "household_size"],
        range_slots=[
            slot_schemas.RangeSlotConfig(
                slot_name="household_size", kind="text_range", spec_key="so_nguoi_su_dung", label="số người sử dụng"
            )
        ],
    )
    monkeypatch.setitem(slot_schemas.CATEGORY_SLOT_SCHEMAS, "fake_fridge_category", fake_schema)

    products = [
        fridge("FR-1", 15_000_000, "3 - 4 người"),
        fridge("FR-2", 22_000_000, "4 - 5 người"),
        fridge("FR-3", 12_000_000, None),
    ]
    result = filter_products("fake_fridge_category", {"budget_max": 16_000_000, "household_size": 4}, products)
    assert result.status == "ok"
    assert [p["product_id"] for p in result.products] == ["FR-1"]


def test_default_category_budget_only_no_range_relax_step():
    products = [pc("PC-1", 15_000_000), pc("PC-2", 25_000_000)]
    result = filter_products("desktop_pc", {"budget_max": 20_000_000}, products)
    assert result.status == "ok"
    assert [p["product_id"] for p in result.products] == ["PC-1"]

    result2 = filter_products("desktop_pc", {"budget_max": 1_000_000}, products)
    # default schema chỉ có 1 bước nới (budget +15%), không có range slot
    assert result2.relaxed_steps == ["increased_budget_15pct"]
