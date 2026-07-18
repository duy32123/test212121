"""
guardrail/validators.py — Module 4 (Validation/Guardrail), triển khai bằng
Guardrails AI thật (`guardrails-ai`, cài qua pip, không copy source repo).

Đây là validator tuỳ chỉnh (local, không cần Guardrails Hub / network) gắn
vào field `items` của output LLM. Nó:
  1. Loại bỏ item có product_id không nằm trong Top N (rejected_items).
  2. Với mỗi field text (headline/pros/cons/recommendation_reason), trích
     claim số và đối chiếu với `known_facts` — claim sai lệch bị thay bằng
     FALLBACK_TEXT, ghi log vào corrections.
  3. Giá hiển thị (`effective_price`) luôn lấy từ record gốc, không lấy
     theo số LLM viết ra.
  4. Sản phẩm có trong Top N nhưng LLM bỏ sót -> vẫn được thêm lại vào kết
     quả (kèm cờ llm_explanation_missing) để không mất sản phẩm hợp lệ.

Guardrails AI không hỗ trợ trả thêm dữ liệu ngoài (corrections/rejected)
qua FailResult, nên dùng "side-channel" hợp lệ của thư viện: ghi vào chính
`metadata` dict truyền vào `guard.parse(metadata=...)` — dict này là mutable
và KHÔNG bị copy trước khi validator chạy (đã kiểm chứng), nên caller đọc
lại được sau khi parse() xong.
"""
from __future__ import annotations

from typing import Any

from guardrails.validator_base import FailResult, PassResult, Validator, register_validator

from app.guardrail.claim_extraction import extract_money_mentions, extract_spec_mentions
from app.guardrail.known_facts import KnownFacts

MONEY_TOLERANCE = 0.03  # 3% — cho phép làm tròn nhẹ ("gần 15 triệu" cho 14.990.000)
SPEC_TOLERANCE = 0.02  # 2% — thông số kỹ thuật nên khớp gần như tuyệt đối

FALLBACK_TEXT = (
    "Thông tin này chưa khớp với dữ liệu catalog nên đã được ẩn để tránh sai lệch — "
    "vui lòng xem thông số gốc bên dưới."
)


def _is_known_value(value: float, known: set[float], tolerance: float) -> bool:
    for k in known:
        denom = max(abs(k), 1)
        if abs(value - k) / denom <= tolerance:
            return True
    return False


def _check_text_field(text: Any, facts: KnownFacts) -> tuple[bool, list[dict]]:
    if not isinstance(text, str) or not text.strip():
        return True, []

    bad_money = [v for v in extract_money_mentions(text) if not _is_known_value(v, facts.money, MONEY_TOLERANCE)]
    bad_specs = [
        s for s in extract_spec_mentions(text) if not _is_known_value(s.value, facts.spec.get(s.unit, set()), SPEC_TOLERANCE)
    ]
    if not bad_money and not bad_specs:
        return True, []

    unverified = [{"type": "money", "value": v} for v in bad_money] + [
        {"type": "spec", "value": s.value, "unit": s.unit} for s in bad_specs
    ]
    return False, unverified


def _validate_and_maybe_replace(text: Any, facts: KnownFacts, product_id: str, field_path: str, corrections: list) -> str:
    ok, unverified = _check_text_field(text, facts)
    if ok:
        return text if isinstance(text, str) else ""
    corrections.append(
        {
            "product_id": product_id,
            "field": field_path,
            "original_text": text,
            "reason": "unverified_numeric_claim",
            "unverified_values": unverified,
        }
    )
    return FALLBACK_TEXT


@register_validator(name="btc/claims-verified", data_type="list")
class ClaimsVerified(Validator):
    """
    Gắn vào field `items` (on='$.items'). `metadata` PHẢI chứa:
      - known_ids: set[str]           product_id hợp lệ (trong Top N)
      - products_by_id: dict[str, dict]  ranked result gốc, key = product_id
      - facts: KnownFacts
      - _corrections / _rejected_items: list (side-channel output, để rỗng ban đầu)
    """

    def validate(self, value, metadata):
        known_ids: set[str] = metadata.get("known_ids", set())
        products_by_id: dict[str, dict] = metadata.get("products_by_id", {})
        facts: KnownFacts = metadata.get("facts") or KnownFacts()
        corrections: list = metadata.setdefault("_corrections", [])
        rejected: list = metadata.setdefault("_rejected_items", [])

        fixed_items = []
        for raw_item in value or []:
            pid = str(raw_item.get("product_id")) if raw_item.get("product_id") is not None else None
            if not pid or pid not in known_ids:
                rejected.append({"product_id": pid, "reason": "unknown_product_id", "raw": raw_item})
                continue

            ranked = products_by_id[pid]
            fixed_items.append(
                {
                    "product_id": pid,
                    "model_code": ranked.get("model_code"),
                    "name": ranked.get("name"),
                    "brand": ranked.get("brand"),
                    "image": ranked.get("image"),
                    "url": ranked.get("url"),
                    "effective_price": ranked.get("effective_price"),
                    "headline": _validate_and_maybe_replace(raw_item.get("headline"), facts, pid, "headline", corrections),
                    "pros": [
                        _validate_and_maybe_replace(t, facts, pid, f"pros[{i}]", corrections)
                        for i, t in enumerate(raw_item.get("pros") or [])
                    ],
                    "cons": [
                        _validate_and_maybe_replace(t, facts, pid, f"cons[{i}]", corrections)
                        for i, t in enumerate(raw_item.get("cons") or [])
                    ],
                    "recommendation_reason": _validate_and_maybe_replace(
                        raw_item.get("recommendation_reason"), facts, pid, "recommendation_reason", corrections
                    ),
                    "matched_reasons": ranked.get("matched_reasons", []),
                    "tradeoffs": ranked.get("tradeoffs", []),
                    "missing_data": ranked.get("missing_data", []),
                    "data_source": {"product_id": ranked.get("product_id"), "model_code": ranked.get("model_code"), "url": ranked.get("url")},
                }
            )

        # Sản phẩm nằm trong Top N nhưng LLM bỏ sót -> thêm lại kèm cờ
        explained_ids = {i["product_id"] for i in fixed_items}
        for pid, ranked in products_by_id.items():
            if pid in explained_ids:
                continue
            fixed_items.append(
                {
                    "product_id": pid,
                    "model_code": ranked.get("model_code"),
                    "name": ranked.get("name"),
                    "brand": ranked.get("brand"),
                    "image": ranked.get("image"),
                    "url": ranked.get("url"),
                    "effective_price": ranked.get("effective_price"),
                    "headline": None,
                    "pros": [],
                    "cons": [],
                    "recommendation_reason": None,
                    "matched_reasons": ranked.get("matched_reasons", []),
                    "tradeoffs": ranked.get("tradeoffs", []),
                    "missing_data": ranked.get("missing_data", []),
                    "data_source": {"product_id": ranked.get("product_id"), "model_code": ranked.get("model_code"), "url": ranked.get("url")},
                    "llm_explanation_missing": True,
                }
            )

        # giữ đúng thứ tự rank ban đầu
        order = {pid: idx for idx, pid in enumerate(products_by_id.keys())}
        fixed_items.sort(key=lambda i: order.get(i["product_id"], 999))

        if fixed_items != value:
            return FailResult(error_message="items corrected/filtered by guardrail", fix_value=fixed_items)
        return PassResult()
