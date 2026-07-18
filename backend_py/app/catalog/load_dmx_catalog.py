"""
catalog/load_dmx_catalog.py — PRODUCTION LOADER cho catalog.

Đọc DUY NHẤT `backend_py/data/products_detail.json` (không gọi
`pd.read_excel` hay bất kỳ thao tác Excel nào ở đây). Mapping field thô ->
canonical hoàn toàn dựa vào `schemas/dmx_registry.json` (qua
`catalog/dmx_registry.py`) — không hardcode tên field/category trong loader.

Nếu `products_detail.json` thiếu file, rỗng, không phải JSON hợp lệ, hoặc
thiếu field cấp 1 bắt buộc (`product_id`) — loader RAISE lỗi rõ ràng
(`DmxCatalogError`), KHÔNG tự tạo dữ liệu giả hay âm thầm trả catalog rỗng.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.catalog.dmx_registry import (
    DmxRegistry,
    DmxRegistryError,
    SINGLE_VALUE_PARSERS,
    apply_spec_field_mapping,
    load_dmx_registry,
)
from app.catalog.parse_specs import effective_price

REQUIRED_TOP_LEVEL_KEY = "product_id"


class DmxCatalogError(Exception):
    """Raise khi products_detail.json thiếu/hỏng cấu trúc — không âm thầm bỏ qua."""


def _clean(value):
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def _apply_top_level_mapping(raw: dict[str, Any], registry: DmxRegistry) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for raw_key, target in registry.top_level_mapping.items():
        raw_value = _clean(raw.get(raw_key))
        if isinstance(target, str):
            mapped[target] = raw_value
        elif isinstance(target, dict):
            key = target.get("key")
            parser_name = target.get("parser")
            if not key or not parser_name:
                raise DmxRegistryError(f"top_level_mapping['{raw_key}'] thiếu 'key' hoặc 'parser'.")
            parser_fn = SINGLE_VALUE_PARSERS.get(parser_name)
            if not parser_fn:
                raise DmxRegistryError(f"top_level parser '{parser_name}' không được hỗ trợ (field '{raw_key}').")
            mapped[key] = parser_fn(raw_value)
        else:
            raise DmxRegistryError(f"top_level_mapping['{raw_key}'] có kiểu không hợp lệ: {type(target)}")
    return mapped


def _build_spec(raw_specs: dict[str, Any], registry: DmxRegistry, category_name_vn: str) -> dict[str, Any]:
    category_cfg = registry.category_config(category_name_vn)
    if not category_cfg:
        return {}
    spec: dict[str, Any] = {}
    for mapping in category_cfg.spec_map:
        raw_value = raw_specs.get(mapping.source_key)
        spec.update(apply_spec_field_mapping(mapping, raw_value))
    return spec


def _is_eligible_for_demo(effective_price_value, spec: dict[str, Any], has_spec_map: bool) -> bool:
    if effective_price_value is None:
        return False
    if not has_spec_map:
        return True
    return any(v is not None for v in spec.values())


def _record_to_product(raw: dict[str, Any], registry: DmxRegistry, index: int) -> dict[str, Any] | None:
    if REQUIRED_TOP_LEVEL_KEY not in raw:
        raise DmxCatalogError(
            f"Record thứ {index} trong products_detail.json thiếu field bắt buộc "
            f"'{REQUIRED_TOP_LEVEL_KEY}' — cấu trúc dữ liệu không khớp mong đợi."
        )

    product_id_raw = raw.get("product_id")
    if product_id_raw is None:
        return None  # sản phẩm thiếu định danh -> không có nguồn để trích dẫn, bỏ qua (không bịa id)

    mapped = _apply_top_level_mapping(raw, registry)

    category_name_vn = _clean(raw.get("category_name"))
    if not category_name_vn:
        return None  # không xác định được category -> không thể lọc/hỏi slot đúng, bỏ qua

    category_slug = registry.slug_for(category_name_vn)
    category_cfg = registry.category_config(category_name_vn)

    raw_specs = raw.get("specs") if isinstance(raw.get("specs"), dict) else {}
    spec = _build_spec(raw_specs, registry, category_name_vn)

    original_price = mapped.get("original_price")
    promotion_price = mapped.get("promotion_price")
    eff_price = effective_price(original_price, promotion_price)

    product_id = str(product_id_raw)
    sku = str(raw.get("productcode")) if raw.get("productcode") not in (None, "") else None

    missing_fields = [k for k, v in spec.items() if v is None]

    return {
        "product_id": product_id,
        # DMX (products_detail.json) không có field model_code riêng biệt như
        # dữ liệu Excel cũ (không có tên model dạng "TBI-18CSD/TPHI" tách
        # bạch) — để None thay vì gán nhầm 'productcode' (là mã vạch, không
        # phải model code người đọc được), tránh gán sai ngữ nghĩa field.
        "model_code": None,
        "sku": sku,
        "name": mapped.get("name"),
        "image": mapped.get("image"),
        "url": mapped.get("url"),
        "category": category_slug,
        "category_name_vn": category_name_vn,
        "category_code": str(raw.get("category_id")) if raw.get("category_id") is not None else None,
        "brand": mapped.get("brand"),
        "brand_id": None,  # DMX không có trường brand_id riêng
        "original_price": original_price,
        "promotion_price": promotion_price,
        "effective_price": eff_price,
        "promotion_text": mapped.get("promotion"),
        "stock_status": "unknown",  # DMX không có tồn kho -> không bịa
        "stock_by_location": {},
        "spec": spec,
        "spec_raw": raw_specs,
        "source": {
            "type": "dmx_json",
            "product_id": product_id,
            "category_name_vn": category_name_vn,
            "source_row": index,
        },
        "data_quality": {
            "eligible_for_demo": _is_eligible_for_demo(eff_price, spec, category_cfg is not None),
            "has_spec_map": category_cfg is not None,
            "missing_fields": missing_fields,
            "warnings": [] if eff_price is not None else ["missing_effective_price"],
        },
    }


def load_catalog_from_json(json_path: Path | str | None = None, registry: DmxRegistry | None = None) -> dict[str, list[dict[str, Any]]]:
    """
    Trả về { category_slug: [product, ...] } đọc từ products_detail.json.
    KHÔNG import pandas — không có đường nào trong hàm này chạm tới Excel.
    """
    from app.config.settings import PRODUCTS_DETAIL_JSON_PATH

    path = Path(json_path) if json_path else PRODUCTS_DETAIL_JSON_PATH
    registry = registry or load_dmx_registry()

    if not path.exists():
        raise DmxCatalogError(
            f"Không tìm thấy {path}. Chạy `python scripts/build_products_detail_json.py "
            "--input <products_detail.xlsx> --output backend_py/data/products_detail.json` "
            "để tạo file này trước, hoặc trỏ đúng đường dẫn."
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_records = json.load(f)
    except json.JSONDecodeError as exc:
        raise DmxCatalogError(f"{path} không phải JSON hợp lệ: {exc}") from exc

    if not isinstance(raw_records, list):
        raise DmxCatalogError(f"{path} phải là một JSON array ở cấp cao nhất, nhận được {type(raw_records).__name__}.")
    if not raw_records:
        raise DmxCatalogError(f"{path} rỗng — không có sản phẩm nào để nạp.")
    if REQUIRED_TOP_LEVEL_KEY not in raw_records[0]:
        raise DmxCatalogError(
            f"Record đầu tiên trong {path} thiếu field '{REQUIRED_TOP_LEVEL_KEY}' — "
            "cấu trúc file không khớp với định dạng products_detail.json mong đợi."
        )

    catalog: dict[str, list[dict[str, Any]]] = {}
    for idx, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            raise DmxCatalogError(f"Record thứ {idx} trong {path} không phải object JSON.")
        product = _record_to_product(raw, registry, idx)
        if product is not None:
            catalog.setdefault(product["category"], []).append(product)

    return catalog
