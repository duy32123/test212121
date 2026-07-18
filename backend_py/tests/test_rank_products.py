from __future__ import annotations

from types import SimpleNamespace

from app.ranking.rank_products import rank_products
from app.retrieval.filter_products import FilterResult


def ac(id_, price, area=None, noise_min=None, noise_max=None, energy_saving=None):
    return {
        "product_id": id_,
        "model_code": id_,
        "category": "air_conditioner",
        "effective_price": price,
        "spec": {
            "area_min_m2": area[0] if area else None,
            "area_max_m2": area[1] if area else None,
            "indoor_noise_min_db": noise_min,
            "indoor_noise_max_db": noise_max,
            "energy_saving_technology": energy_saving or [],
        },
    }


def state_with(category, slots):
    return SimpleNamespace(category=category, slots=slots)


def test_top_n_default_3_and_source_attached():
    retrieval = FilterResult(
        status="ok",
        products=[
            ac("AC-1", 10_000_000, area=(15, 20), noise_min=24, noise_max=40),
            ac("AC-2", 11_000_000, area=(15, 20), noise_min=26, noise_max=42),
            ac("AC-3", 12_000_000, area=(15, 20), noise_min=28, noise_max=43),
            ac("AC-4", 13_000_000, area=(15, 20), noise_min=35, noise_max=45),
        ],
    )
    state = state_with(
        "air_conditioner", {"budget_max": 20_000_000, "room_area_m2": 18, "installation_location": "phòng ngủ"}
    )
    result = rank_products(retrieval, state)
    assert len(result.results) == 3
    assert result.results[0]["rank"] == 1
    assert result.results[0]["product_id"] == "AC-1"
    assert result.results[0]["source"]["product_id"] == "AC-1"


def test_score_drops_for_mismatched_area_and_noise():
    good = ac("GOOD", 10_000_000, area=(15, 20), noise_min=24, noise_max=40)
    bad = ac("BAD", 10_000_000, area=(30, 40), noise_min=44, noise_max=55)
    retrieval = FilterResult(status="relaxed", relaxed_steps=["dropped_room_area_m2_constraint"], products=[bad, good])
    state = state_with(
        "air_conditioner", {"budget_max": 12_000_000, "room_area_m2": 18, "installation_location": "phòng ngủ"}
    )
    result = rank_products(retrieval, state)
    assert result.results[0]["product_id"] == "GOOD"
    assert result.results[0]["total_score"] > result.results[1]["total_score"]
    assert "dropped_room_area_m2_constraint" in " ".join(result.results[1]["tradeoffs"])


def test_missing_spec_data_not_fabricated_gets_neutral_score():
    retrieval = FilterResult(status="ok", products=[ac("NULLS", 9_000_000)])
    state = state_with(
        "air_conditioner",
        {"budget_max": 12_000_000, "room_area_m2": 18, "installation_location": "phòng ngủ", "power_saving_priority": True},
    )
    result = rank_products(retrieval, state)
    top = result.results[0]
    assert "room_area_m2" in top["missing_data"]
    assert top["score_breakdown"]["room_area_m2"]["score"] == 50


def test_not_ready_and_no_results_passthrough():
    assert rank_products(FilterResult(status="not_ready", missing_slots=["budget_max"]), None).status == "not_ready"
    assert rank_products(FilterResult(status="no_results", message="x"), None).status == "no_results"


def test_generic_category_without_range_slots_still_ranks_by_budget():
    products = [
        {"product_id": "PC-1", "model_code": "PC-1", "category": "desktop_pc", "effective_price": 10_000_000, "spec": {}},
        {"product_id": "PC-2", "model_code": "PC-2", "category": "desktop_pc", "effective_price": 25_000_000, "spec": {}},
    ]
    retrieval = FilterResult(status="ok", products=products)
    state = state_with("desktop_pc", {"budget_max": 15_000_000})
    result = rank_products(retrieval, state)
    assert result.results[0]["product_id"] == "PC-1"
