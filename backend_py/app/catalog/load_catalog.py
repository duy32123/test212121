"""
catalog/load_catalog.py — nạp Spec_cate_gia.xlsx theo đúng mapping trong
registry.json, chuẩn hoá thành product dict khớp `_base.schema.json` +
schema riêng từng category. Hoạt động cho CẢ 14 category — không hardcode
category nào trong hàm parse chính; chỉ deep_fields của air_conditioner có
dispatch riêng vì đó là category duy nhất registry.json khai `deep_parse: true`.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.catalog.registry import CategoryConfig, FieldMapping, Registry, load_registry
from app.catalog.parse_specs import (
    effective_price,
    parse_efficiency_index,
    parse_inverter,
    parse_list_column,
    parse_noise_reading,
    parse_number,
    parse_range_generic,
    parse_star_rating,
    parse_year,
)

_IDENTITY_COLUMNS = [
    "model_code",
    "sku",
    "productidweb",
    "category_code",
    "brand_id",
    "brand",
    "giá gốc",
    "giá khuyến mãi",
    "khuyến mãi quà",
]

# Dispatch cho deep_fields — CHỈ air_conditioner dùng tới (registry.json là
# category duy nhất có deep_parse=True). Thêm category mới có deep_fields
# thì chỉ cần thêm entry vào dict này, không sửa hàm load chính.
_DEEP_FIELD_PARSERS: dict[str, Any] = {
    "product_year": lambda raw: parse_year(raw),
    "area_min_m2": lambda raw: (r.min if (r := parse_range_generic(raw)) else None),
    "area_max_m2": lambda raw: (r.max if (r := parse_range_generic(raw)) else None),
    "cooling_capacity_btu": lambda raw: (int(n) if (n := parse_number(raw)) is not None else None),
    "energy_stars": lambda raw: parse_star_rating(raw),
    "cspf": lambda raw: parse_efficiency_index(raw),
    "indoor_noise_min_db": lambda raw: parse_noise_reading(raw).indoor_min_db,
    "indoor_noise_max_db": lambda raw: parse_noise_reading(raw).indoor_max_db,
    "outdoor_noise_db": lambda raw: parse_noise_reading(raw).outdoor_db,
    "inverter": lambda raw: parse_inverter(raw),
}


def _clean_scalar(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def _apply_mapping(row: pd.Series, mapping: FieldMapping) -> Any:
    raw = row.get(mapping.source_column)
    raw = _clean_scalar(raw)
    if raw is None:
        return [] if mapping.type == "list" else None

    if mapping.type == "list":
        return parse_list_column(raw)
    if mapping.type in ("number",):
        return parse_number(raw)
    if mapping.type == "integer":
        n = parse_number(raw)
        return int(n) if n is not None else None
    if mapping.type == "boolean":
        return bool(raw) if not isinstance(raw, str) else raw.strip().lower() in ("có", "yes", "true", "1")
    return str(raw)


def _build_spec(row: pd.Series, cfg: CategoryConfig) -> dict[str, Any]:
    spec: dict[str, Any] = {}
    for mapping in cfg.mappings:
        if mapping.source_column in cfg.drop_columns:
            continue
        spec[mapping.key] = _apply_mapping(row, mapping)

    if cfg.deep_parse:
        for deep_field in cfg.deep_fields:
            raw = _clean_scalar(row.get(deep_field.source_column))
            parser = _DEEP_FIELD_PARSERS.get(deep_field.key)
            spec[deep_field.key] = parser(raw) if parser else None

    return spec


def _row_to_product(row: pd.Series, cfg: CategoryConfig, row_index: int) -> dict[str, Any] | None:
    model_code = _clean_scalar(row.get("model_code"))
    if model_code is None:
        return None  # không có định danh -> không có nguồn để trích dẫn (Module 4), bỏ qua

    original_price_raw = _clean_scalar(row.get("giá gốc"))
    promo_price_raw = _clean_scalar(row.get("giá khuyến mãi"))
    original_price = int(original_price_raw) if isinstance(original_price_raw, (int, float)) else None
    promo_price = int(promo_price_raw) if isinstance(promo_price_raw, (int, float)) else None

    spec = _build_spec(row, cfg)

    missing_fields = [k for k, v in spec.items() if v is None or v == []]
    eff_price = effective_price(original_price, promo_price)

    return {
        "product_id": str(model_code),
        "model_code": str(model_code),
        "sku": str(_clean_scalar(row.get("sku"))) if _clean_scalar(row.get("sku")) is not None else None,
        "product_web_id": (
            str(_clean_scalar(row.get("productidweb"))) if _clean_scalar(row.get("productidweb")) is not None else None
        ),
        "category": cfg.category,
        "category_code": (
            str(_clean_scalar(row.get("category_code"))) if _clean_scalar(row.get("category_code")) is not None else None
        ),
        "brand": _clean_scalar(row.get("brand")),
        "brand_id": str(_clean_scalar(row.get("brand_id"))) if _clean_scalar(row.get("brand_id")) is not None else None,
        "original_price": original_price,
        "promotion_price": promo_price,
        "effective_price": eff_price,
        "promotions": parse_list_column(_clean_scalar(row.get("khuyến mãi quà"))),
        "stock_status": "unknown",
        "stock_by_location": {},
        "spec": spec,
        "source": {
            "type": "btc_excel",
            "sheet": cfg.sheet_name,
            "source_row": row_index,
            "sku": str(_clean_scalar(row.get("sku")) or ""),
        },
        "data_quality": {
            "eligible_for_demo": eff_price is not None,
            "missing_fields": missing_fields,
            "warnings": [] if eff_price is not None else ["missing_effective_price"],
        },
    }


def load_catalog_from_excel(xlsx_path, registry: Registry | None = None) -> dict[str, list[dict[str, Any]]]:
    """
    Trả về { category_slug: [product, ...] } cho TẤT CẢ category có trong
    registry.json. Đọc trực tiếp Spec_cate_gia.xlsx — không có bước trung
    gian nào có thể làm sai lệch dữ liệu nguồn.
    """
    registry = registry or load_registry()
    workbook = pd.ExcelFile(xlsx_path)
    catalog: dict[str, list[dict[str, Any]]] = {}

    for sheet_name, cfg in registry.categories_by_sheet.items():
        if sheet_name not in workbook.sheet_names:
            catalog[cfg.category] = []
            continue
        df = pd.read_excel(workbook, sheet_name=sheet_name)
        products = []
        for idx, row in df.iterrows():
            product = _row_to_product(row, cfg, int(idx) + 2)  # +2: header row + 1-indexed
            if product is not None:
                products.append(product)
        catalog[cfg.category] = products

    return catalog
