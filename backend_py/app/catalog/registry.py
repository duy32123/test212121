"""
catalog/registry.py — nạp `schemas/registry.json` (do BTC/đối tác cung cấp),
mô tả mapping từ mỗi sheet Excel sang 1 category + danh sách cột cần đọc.

Đây là nguồn cấu hình DUY NHẤT cho việc parse catalog — không hardcode tên
cột/category nào trong code. Thêm category mới = thêm entry trong
registry.json + schema JSON tương ứng, KHÔNG cần sửa code Python.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config.settings import LEGACY_REGISTRY_PATH as REGISTRY_PATH
from app.config.settings import SCHEMAS_DIR


@dataclass(frozen=True)
class FieldMapping:
    key: str
    source_column: str
    type: str  # "string" | "list" | "number" | "integer" | "boolean"


@dataclass(frozen=True)
class CategoryConfig:
    sheet_name: str
    category: str
    mappings: list[FieldMapping]
    deep_fields: list[FieldMapping]
    list_columns: list[str]
    drop_columns: list[str]
    deep_parse: bool
    schema_file: str


@dataclass(frozen=True)
class Registry:
    version: int
    base_schema: str
    categories_by_sheet: dict[str, CategoryConfig]

    def all_categories(self) -> list[str]:
        return [c.category for c in self.categories_by_sheet.values()]

    def config_for_category(self, category: str) -> CategoryConfig | None:
        for cfg in self.categories_by_sheet.values():
            if cfg.category == category:
                return cfg
        return None


def _parse_mappings(raw: list[dict[str, Any]]) -> list[FieldMapping]:
    return [FieldMapping(key=m["key"], source_column=m["source_column"], type=m["type"]) for m in raw]


@lru_cache(maxsize=1)
def load_registry() -> Registry:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    categories_by_sheet: dict[str, CategoryConfig] = {}
    for sheet_name, cfg in raw["sheets"].items():
        categories_by_sheet[sheet_name] = CategoryConfig(
            sheet_name=sheet_name,
            category=cfg["category"],
            mappings=_parse_mappings(cfg.get("mappings", [])),
            deep_fields=_parse_mappings(cfg.get("deep_fields", [])),
            list_columns=cfg.get("list_columns", []),
            drop_columns=cfg.get("drop_columns", []),
            deep_parse=cfg.get("deep_parse", False),
            schema_file=cfg["schema"],
        )

    return Registry(version=raw.get("version", 1), base_schema=raw.get("base_schema", "_base.schema.json"), categories_by_sheet=categories_by_sheet)


@lru_cache(maxsize=None)
def load_product_schema(schema_file: str) -> dict[str, Any]:
    with open(SCHEMAS_DIR / schema_file, "r", encoding="utf-8") as f:
        return json.load(f)
