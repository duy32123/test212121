"""
guardrail/known_facts.py — port từ bản Node (validation/knownFacts.js).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations


@dataclass
class KnownFacts:
    money: set[float] = field(default_factory=set)
    spec: dict[str, set[float]] = field(default_factory=lambda: {"m²": set(), "dB": set(), "lít": set(), "người": set()})


def build_known_facts(ranking_results: list[dict], slots: dict) -> KnownFacts:
    facts = KnownFacts()
    slots = slots or {}

    if isinstance(slots.get("budget_max"), (int, float)):
        facts.money.add(slots["budget_max"])
    if isinstance(slots.get("budget_min"), (int, float)):
        facts.money.add(slots["budget_min"])
    if isinstance(slots.get("room_area_m2"), (int, float)):
        facts.spec["m²"].add(slots["room_area_m2"])
    if isinstance(slots.get("household_size"), (int, float)):
        facts.spec["người"].add(slots["household_size"])
    if isinstance(slots.get("capacity_liters"), (int, float)):
        facts.spec["lít"].add(slots["capacity_liters"])

    prices = []
    for item in ranking_results or []:
        price = item.get("effective_price")
        if isinstance(price, (int, float)):
            facts.money.add(price)
            prices.append(price)

        src = item.get("source") or {}
        spec = src.get("spec") or {}

        area_min, area_max = spec.get("area_min_m2"), spec.get("area_max_m2")
        if isinstance(area_min, (int, float)):
            facts.spec["m²"].add(area_min)
        if isinstance(area_max, (int, float)):
            facts.spec["m²"].add(area_max)

        noise_min, noise_max, noise_out = (
            spec.get("indoor_noise_min_db"),
            spec.get("indoor_noise_max_db"),
            spec.get("outdoor_noise_db"),
        )
        for v in (noise_min, noise_max, noise_out):
            if isinstance(v, (int, float)):
                facts.spec["dB"].add(v)

    for a, b in combinations(prices, 2):
        facts.money.add(abs(a - b))

    return facts
