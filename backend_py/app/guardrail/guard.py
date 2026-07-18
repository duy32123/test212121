from __future__ import annotations

from dataclasses import dataclass

from guardrails import Guard

import app.config.settings  # noqa: F401 — side-effect: tắt telemetry guardrails-ai
from app.guardrail.known_facts import build_known_facts
from app.guardrail.output_schema import ExplanationOutput
from app.guardrail.validators import ClaimsVerified


@dataclass
class GuardBundle:
    guard: Guard
    metadata: dict


def build_guard_for_ranking(ranking_results: list[dict], slots: dict) -> GuardBundle:
    known_ids = {str(r["product_id"]) for r in ranking_results}
    products_by_id = {str(r["product_id"]): r for r in ranking_results}
    facts = build_known_facts(ranking_results, slots)

    guard = Guard.for_pydantic(ExplanationOutput)
    guard.use(ClaimsVerified(on_fail="fix"), on="$.items")

    metadata = {
        "known_ids": known_ids,
        "products_by_id": products_by_id,
        "facts": facts,
        "_corrections": [],
        "_rejected_items": [],
    }
    return GuardBundle(guard=guard, metadata=metadata)
