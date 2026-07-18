"""
retrieval/retrieve_for_state.py — điều phối lấy catalog và gọi filter_products.

Đặc biệt xử lý category "pc_may_in" (gộp desktop + màn hình + máy in trong
DMX): lọc sub-type dựa trên slot use_case để không trả lẫn sản phẩm.
Sub-type detection dựa trên TÊN sản phẩm + spec key có thật (không bịa field).
"""
from __future__ import annotations

from app.catalog.catalog_store import get_catalog
from app.conversation.missing_slots import compute_missing_slots
from app.conversation.state import ConversationState
from app.retrieval.filter_products import FilterResult, filter_products


# Mapping use_case → keyword để lọc tên sản phẩm trong pc_may_in.
# Chỉ lọc khi khách đã nêu use_case RÕ RÀNG — không đoán mò nếu không có.
_PC_SUBTYPE_NAME_KEYWORDS: dict[str, list[str]] = {
    "monitor":  ["màn hình"],
    "desktop":  ["pc ", "máy tính để bàn", "desktop", "singpc", "rosa ", "asus rezo"],
    "printer":  ["máy in", "máy quét"],
}

# Spec key duy nhất có trong data để phân biệt sub-type (từ phân tích coverage):
#   monitors: có "Tấm nền" + "Tần số quét"
#   desktops: có "Công nghệ CPU"
#   printers: có "Tốc độ in"
_PC_SUBTYPE_SPEC_KEYS: dict[str, list[str]] = {
    "monitor": ["Tấm nền", "Tần số quét"],
    "desktop": ["Công nghệ CPU"],
    "printer": ["Tốc độ in"],
}


def _detect_pc_subtype(product: dict) -> str:
    """Phát hiện sub-type của sản phẩm trong pc_may_in.
    Trả về 'monitor' | 'desktop' | 'printer' | 'other'.
    Chỉ dựa vào field CÓ THẬT — không bịa."""
    spec_raw = product.get("spec_raw") or product.get("spec") or {}
    name = (product.get("name") or "").lower()

    # Kiểm tra spec key đặc trưng trước (chính xác hơn tên)
    if any(k in spec_raw for k in _PC_SUBTYPE_SPEC_KEYS["monitor"]):
        return "monitor"
    if any(k in spec_raw for k in _PC_SUBTYPE_SPEC_KEYS["desktop"]):
        return "desktop"
    if any(k in spec_raw for k in _PC_SUBTYPE_SPEC_KEYS["printer"]):
        return "printer"

    # Fallback: kiểm tra tên sản phẩm
    for subtype, keywords in _PC_SUBTYPE_NAME_KEYWORDS.items():
        if any(kw in name for kw in keywords):
            return subtype

    return "other"


def _filter_pc_subtype(products: list[dict], use_case: str | None) -> list[dict]:
    """Lọc sub-type pc_may_in theo use_case của khách.
    Nếu use_case không rõ → trả tất cả (không loại gì).
    Nếu use_case rõ → chỉ trả đúng sub-type tương ứng.
    """
    if not use_case:
        return products

    uc_lower = use_case.lower()

    # Map use_case string → sub-type
    target_subtype: str | None = None
    if any(k in uc_lower for k in ["màn hình", "monitor", "screen"]):
        target_subtype = "monitor"
    elif any(k in uc_lower for k in ["pc", "desktop", "máy tính để bàn", "máy tính bàn", "gaming"]):
        target_subtype = "desktop"
    elif any(k in uc_lower for k in ["máy in", "printer", "in ấn"]):
        target_subtype = "printer"

    if target_subtype is None:
        return products  # use_case không map được → không lọc thêm

    filtered = [p for p in products if _detect_pc_subtype(p) == target_subtype]
    # Fallback: nếu không tìm thấy sub-type → trả tất cả (không để rỗng)
    return filtered if filtered else products


def retrieve_for_state(state: ConversationState, catalog_override: dict | None = None) -> FilterResult:
    missing_slots = compute_missing_slots(state)
    if missing_slots:
        return FilterResult(status="not_ready", missing_slots=missing_slots)

    catalog = catalog_override if catalog_override is not None else get_catalog()
    products = catalog.get(state.category, [])

    # Pc, máy in: lọc sub-type TRƯỚC filter_products để tránh trộn sản phẩm
    if state.category == "pc_may_in":
        products = _filter_pc_subtype(products, state.slots.get("use_case"))

    return filter_products(state.category, state.slots, products)
