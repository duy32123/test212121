from __future__ import annotations

from app.guardrail.known_facts import build_known_facts


def ranked(id_, price, area_min=None, area_max=None, noise_min=None, noise_max=None):
    return {
        "product_id": id_,
        "effective_price": price,
        "source": {"spec": {"area_min_m2": area_min, "area_max_m2": area_max, "indoor_noise_min_db": noise_min, "indoor_noise_max_db": noise_max}},
    }


def test_collects_prices_budget_and_spec_ranges():
    ranking_results = [
        ranked("A", 12_000_000, area_min=15, area_max=20, noise_min=29, noise_max=45),
        ranked("B", 18_000_000, area_min=20, area_max=30),
    ]
    facts = build_known_facts(ranking_results, {"budget_max": 20_000_000, "room_area_m2": 18})

    assert {12_000_000, 18_000_000, 20_000_000}.issubset(facts.money)
    assert {15, 20, 30, 18}.issubset(facts.spec["m²"])
    assert {29, 45}.issubset(facts.spec["dB"])


def test_includes_price_differences_for_comparison_claims():
    ranking_results = [ranked("A", 12_000_000), ranked("B", 15_000_000)]
    facts = build_known_facts(ranking_results, {})
    assert 3_000_000 in facts.money


def test_handles_empty_input():
    facts = build_known_facts([], {})
    assert facts.money == set()
    assert facts.spec["m²"] == set()
