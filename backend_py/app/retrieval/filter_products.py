"""
retrieval/filter_products.py — Module 2 (Retrieval/Filter).

Lọc bằng CODE trên catalog thật (không dùng LLM). Tổng quát cho MỌI
category thông qua `RangeSlotConfig` khai báo trong slot_schemas.py, thay
vì viết matcher riêng cho từng category như bản cũ (nguồn gốc của bug
"category lạ bị rơi vào nhánh máy lạnh").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.catalog.parse_specs import Range, parse_number, parse_range_generic
from app.conversation.slot_schemas import RangeSlotConfig, get_slot_schema


def _resolve_product_range(product: dict[str, Any], cfg: RangeSlotConfig) -> Range | None:
    spec = product.get("spec", {})
    if cfg.kind == "two_field":
        lo = spec.get(cfg.min_spec_key)
        hi = spec.get(cfg.max_spec_key)
        if lo is None and hi is None:
            return None
        if lo is None:
            lo = hi
        return Range(min=lo, max=hi)

    if cfg.kind == "text_range":
        return parse_range_generic(spec.get(cfg.spec_key))

    if cfg.kind == "text_number_tolerance":
        n = parse_number(spec.get(cfg.spec_key))
        if n is None:
            return None
        return Range(min=n * cfg.tolerance_lo, max=n * cfg.tolerance_hi)

    return None


def _matches_budget(product: dict[str, Any], slots: dict[str, Any], budget_multiplier: float) -> bool:
    price = product.get("effective_price")
    if price is None:
        return False
    budget_max = slots.get("budget_max")
    budget_min = slots.get("budget_min")
    if budget_max is not None and price > budget_max * budget_multiplier:
        return False
    if budget_min is not None and price < budget_min:
        return False
    return True


def _matches_range_slots(product: dict[str, Any], slots: dict[str, Any], range_slots: list[RangeSlotConfig]) -> bool:
    for cfg in range_slots:
        requested = slots.get(cfg.slot_name)
        if requested is None:
            continue  # khách chưa cho slot này -> không dùng để loại
        product_range = _resolve_product_range(product, cfg)
        if product_range is None or not product_range.contains(requested):
            return False
    return True


def _matches_brand(product: dict[str, Any], slots: dict[str, Any]) -> bool:
    """brand là field CÓ THẬT trong dữ liệu sản phẩm (product["brand"]) —
    lọc an toàn, không suy diễn/bịa thông số. Không phân biệt hoa/thường,
    không dấu (khớp qua normalize_text)."""
    requested = slots.get("brand")
    if not requested:
        return True
    from app.conversation.nlu_lexicon import normalize_text

    product_brand = product.get("brand")
    if not product_brand:
        return False
    return normalize_text(product_brand) == normalize_text(requested)


def _no_results_message(category: str) -> str:
    return (
        f"Hiện chưa tìm thấy sản phẩm ({category}) phù hợp trong catalog theo đúng yêu cầu, "
        "kể cả khi đã nới ngân sách và một số ràng buộc. Chưa có dữ liệu phù hợp để đề xuất — "
        "không tự bịa sản phẩm."
    )


@dataclass
class FilterResult:
    status: str  # "ok" | "relaxed" | "no_results" | "not_ready"
    relaxed_steps: list[str] = field(default_factory=list)
    products: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None
    missing_slots: list[str] = field(default_factory=list)


def filter_products(category: str, slots: dict[str, Any], products: list[dict[str, Any]]) -> FilterResult:
    schema = get_slot_schema(category)
    range_slots = schema.range_slots
    has_brand = bool(slots.get("brand"))

    range_slot_names = "_".join(rs.slot_name for rs in range_slots) or "range"
    if has_brand:
        range_slot_names = f"{range_slot_names}_brand" if range_slots else "brand"

    steps = [
        ("strict", {"ignore_ranges": False, "ignore_brand": False, "budget_multiplier": 1.0}),
    ]
    if range_slots or has_brand:
        steps.append((f"dropped_{range_slot_names}_constraint", {"ignore_ranges": True, "ignore_brand": True, "budget_multiplier": 1.0}))
    steps.append(("increased_budget_15pct", {"ignore_ranges": bool(range_slots), "ignore_brand": has_brand, "budget_multiplier": 1.15}))

    for i, (step_name, opts) in enumerate(steps):
        matched = [
            p
            for p in products
            if _matches_budget(p, slots, opts["budget_multiplier"])
            and (opts["ignore_ranges"] or _matches_range_slots(p, slots, range_slots))
            and (opts["ignore_brand"] or _matches_brand(p, slots))
        ]
        if matched:
            relaxed = [s for s, _ in steps[1 : i + 1]]
            return FilterResult(status="ok" if i == 0 else "relaxed", relaxed_steps=relaxed, products=matched)

    return FilterResult(
        status="no_results",
        relaxed_steps=[s for s, _ in steps[1:]],
        products=[],
        message=_no_results_message(category),
    )
