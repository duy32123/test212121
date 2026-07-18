"""
guardrail/claim_extraction.py — port từ bản Node (validation/extractClaims.js).
Trích claim số trong văn bản do LLM sinh ra để đối chiếu lại với dữ liệu thật.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


def _to_number(raw: str) -> float:
    return float(raw.replace(",", "."))


def extract_money_mentions(text: str | None) -> list[float]:
    if not isinstance(text, str) or not text:
        return []
    results: list[float] = []

    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(triệu|trieu|tr)\b", text, re.IGNORECASE):
        results.append(round(_to_number(m.group(1)) * 1_000_000))

    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{3}){2,})\s*(đ|vnđ|vnd|₫)?", text, re.IGNORECASE):
        digits = re.sub(r"[.,]", "", m.group(1))
        results.append(float(digits))

    return results


@dataclass(frozen=True)
class SpecMention:
    value: float
    unit: str


_SPEC_UNIT_PATTERNS = [
    ("m²", re.compile(r"(\d+(?:[.,]\d+)?)\s*(m²|m2)(?![a-zA-Z0-9])", re.IGNORECASE)),
    ("dB", re.compile(r"(\d+(?:[.,]\d+)?)\s*(dB|db)(?![a-zA-Z0-9])", re.IGNORECASE)),
    ("lít", re.compile(r"(\d+(?:[.,]\d+)?)\s*(lít|lit)(?![a-zA-Z0-9])", re.IGNORECASE)),
    ("người", re.compile(r"(\d+(?:[.,]\d+)?)\s*người(?![a-zA-Z0-9])", re.IGNORECASE)),
]


def extract_spec_mentions(text: str | None) -> list[SpecMention]:
    if not isinstance(text, str) or not text:
        return []
    results: list[SpecMention] = []
    for unit, pattern in _SPEC_UNIT_PATTERNS:
        for m in pattern.finditer(text):
            results.append(SpecMention(value=_to_number(m.group(1)), unit=unit))
    return results
