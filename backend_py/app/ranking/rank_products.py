"""
ranking/rank_products.py — Module 3 (Ranking), rule-based, không dùng LLM.

Tổng quát cho MỌI category: chấm điểm dựa trên `range_slots` khai báo
trong slot_schemas.py (generic, không viết hàm rank riêng theo category),
cộng thêm 1-2 tiêu chí "kiểm tra sự tồn tại của field trong spec" (không
kiểm tra tên category) để tránh hardcode — ví dụ độ ồn chỉ được chấm nếu
sản phẩm CÓ field 'indoor_noise_min_db', bất kể đó là category gì.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.conversation.slot_schemas import get_slot_schema
from app.retrieval.filter_products import FilterResult, _resolve_product_range

NEUTRAL = 50
DEFAULT_TOP_N = 3


def _clamp(n: float) -> int:
    return max(0, min(100, round(n)))


def _product_id(product: dict[str, Any]) -> str:
    return str(product.get("product_id") or product.get("model_code") or product.get("sku") or "")


def _budget_score(product, slots, reasons, tradeoffs) -> dict:
    price = product.get("effective_price")
    if price is None:
        return {"score": NEUTRAL, "detail": "Thiếu giá hiệu lực; dùng điểm trung lập."}

    budget_max = slots.get("budget_max")
    budget_min = slots.get("budget_min")
    if budget_max is None and budget_min is None:
        return {"score": NEUTRAL, "detail": "Khách chưa đặt ràng buộc ngân sách."}

    score = 100.0
    if budget_max is not None:
        if price <= budget_max:
            ratio = price / budget_max
            score = 100 if ratio >= 0.75 else 90 if ratio >= 0.55 else 80
            reasons.append("Giá nằm trong ngân sách yêu cầu.")
        else:
            over = (price - budget_max) / budget_max
            score = 65 if over <= 0.15 else 40 if over <= 0.3 else 15
            tradeoffs.append("Giá vượt ngân sách yêu cầu.")
    if budget_min is not None and price < budget_min:
        score = min(score, 75)
        tradeoffs.append("Giá thấp hơn khoảng ngân sách tối thiểu khách nêu.")

    return {"score": _clamp(score), "detail": f"Giá hiệu lực {price}."}


def _range_slot_score(product, slots, cfg, missing, reasons, tradeoffs) -> dict | None:
    requested = slots.get(cfg.slot_name)
    if requested is None:
        return None  # khách không cho slot này -> không chấm tiêu chí này

    product_range = _resolve_product_range(product, cfg)
    if product_range is None:
        missing.append(cfg.slot_name)
        return {"score": NEUTRAL, "detail": f"Thiếu dữ liệu {cfg.label}; dùng điểm trung lập."}

    if product_range.contains(requested):
        reasons.append(f"Phù hợp {cfg.label}.")
        return {"score": 100, "detail": f"{requested} nằm trong khoảng {product_range.min}-{product_range.max or '∞'}."}

    mid = product_range.min if product_range.max is None else (product_range.min + product_range.max) / 2
    denom = max(requested, mid, 1)
    diff = abs(requested - mid)
    score = _clamp(100 - (diff / denom) * 100)
    tradeoffs.append(f"Không khớp hoàn toàn {cfg.label}.")
    return {"score": score, "detail": f"{requested} ngoài khoảng {product_range.min}-{product_range.max or '∞'}."}


def _has_energy_saving_signal(spec: dict[str, Any]) -> str | None:
    for key, value in spec.items():
        if "tiet_kiem" not in key and "energy_saving" not in key:
            continue
        if isinstance(value, list) and value:
            return ", ".join(value[:3])
        if isinstance(value, str) and value.strip():
            return value
    return None


def _power_saving_score(product, slots, missing, reasons) -> dict:
    if not slots.get("power_saving_priority"):
        return {"score": NEUTRAL, "detail": "Khách không ưu tiên tiết kiệm điện."}
    signal = _has_energy_saving_signal(product.get("spec", {}))
    if signal is None:
        missing.append("power_saving_tech")
        return {"score": NEUTRAL, "detail": "Thiếu dữ liệu công nghệ tiết kiệm điện; dùng điểm trung lập."}
    reasons.append("Có công nghệ tiết kiệm điện.")
    return {"score": 90, "detail": signal}


def _battery_score(product, slots, missing, reasons, tradeoffs) -> dict | None:
    """Chấm điểm 'pin trâu' cho đồng hồ thông minh / tablet / micro.
    Chỉ chấm nếu sản phẩm có field battery_life_text hoặc battery_mah_text
    trong spec (tồn tại thực tế, không bịa)."""
    spec = product.get("spec", {})
    battery_field = spec.get("battery_life_text") or spec.get("battery_mah_text")
    if battery_field is None:
        return None  # category này không có dữ liệu pin → không chấm
    wants_battery = slots.get("battery_priority")
    if not wants_battery:
        return {"score": NEUTRAL, "detail": "Khách không nêu ưu tiên pin trâu."}
    reasons.append("Có thông tin pin.")
    return {"score": 80, "detail": f"Pin: {battery_field}"}


def _noise_score(product, slots, missing, reasons, tradeoffs) -> dict | None:
    spec = product.get("spec", {})
    if "indoor_noise_min_db" not in spec:
        return None  # category này không có dữ liệu độ ồn -> không chấm tiêu chí này
    wants_quiet = bool(slots.get("noise_priority")) or slots.get("installation_location") == "phòng ngủ"
    if not wants_quiet:
        return {"score": NEUTRAL, "detail": "Khách không nêu ưu tiên độ ồn thấp."}
    quiet = spec.get("indoor_noise_min_db")
    if quiet is None:
        missing.append("indoor_noise_min_db")
        return {"score": NEUTRAL, "detail": "Thiếu dữ liệu độ ồn; dùng điểm trung lập."}
    score = 100 if quiet <= 25 else 90 if quiet <= 30 else 75 if quiet <= 35 else 55 if quiet <= 40 else 35
    (reasons if score >= 75 else tradeoffs).append("Độ ồn phù hợp nhu cầu yên tĩnh." if score >= 75 else "Độ ồn có thể chưa tối ưu.")
    return {"score": score, "detail": f"Độ ồn thấp nhất {quiet} dB."}


def _score_product(product: dict[str, Any], category: str, slots: dict[str, Any], relaxed: list[str]) -> dict[str, Any]:
    missing: list[str] = []
    reasons: list[str] = []
    tradeoffs: list[str] = []
    if relaxed:
        tradeoffs.append(f"Kết quả đã nới ràng buộc: {', '.join(relaxed)}.")

    breakdown: dict[str, dict] = {"budget": _budget_score(product, slots, reasons, tradeoffs)}

    schema = get_slot_schema(category)
    for cfg in schema.range_slots:
        result = _range_slot_score(product, slots, cfg, missing, reasons, tradeoffs)
        if result is not None:
            breakdown[cfg.slot_name] = result

    breakdown["power_saving"] = _power_saving_score(product, slots, missing, reasons)

    noise_result = _noise_score(product, slots, missing, reasons, tradeoffs)
    if noise_result is not None:
        breakdown["noise"] = noise_result

    battery_result = _battery_score(product, slots, missing, reasons, tradeoffs)
    if battery_result is not None:
        breakdown["battery"] = battery_result

    total = _clamp(sum(b["score"] for b in breakdown.values()) / len(breakdown)) if breakdown else NEUTRAL

    return {
        "product": product,
        "product_id": _product_id(product),
        "model_code": product.get("model_code"),
        "name": product.get("name"),
        "brand": product.get("brand"),
        "image": product.get("image"),
        "url": product.get("url"),
        "effective_price": product.get("effective_price"),
        "total_score": total,
        "score_breakdown": breakdown,
        "matched_reasons": reasons,
        "tradeoffs": tradeoffs,
        "missing_data": sorted(set(missing)),
        "relaxed_constraints": relaxed,
        "source": json.loads(json.dumps(product)),  # deep copy, tránh alias
    }


@dataclass
class RankingResult:
    status: str  # "ok" | "relaxed" | "no_results" | "not_ready"
    relaxed_steps: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None
    missing_slots: list[str] = field(default_factory=list)


def rank_products(retrieval: FilterResult, state, top_n: int = DEFAULT_TOP_N) -> RankingResult:
    if retrieval is None or retrieval.status == "not_ready":
        return RankingResult(status="not_ready", missing_slots=retrieval.missing_slots if retrieval else [])

    if retrieval.status == "no_results" or not retrieval.products:
        return RankingResult(status="no_results", message=retrieval.message or "Không có sản phẩm để xếp hạng.")

    category = state.category
    slots = state.slots
    relaxed = retrieval.relaxed_steps if retrieval.status == "relaxed" else []

    scored = [_score_product(p, category, slots, relaxed) for p in retrieval.products]
    scored.sort(key=lambda r: (-r["total_score"], r["effective_price"] if r["effective_price"] is not None else float("inf"), r["product_id"]))

    top = scored[:top_n]
    for i, r in enumerate(top):
        r["rank"] = i + 1

    return RankingResult(status=retrieval.status, relaxed_steps=retrieval.relaxed_steps, results=top)
