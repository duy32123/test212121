"""
scripts/build_products_detail_json.py — CÔNG CỤ CHUẨN BỊ DỮ LIỆU OFFLINE.

Đây là script chạy 1 lần (không phải một phần của production runtime) để
chuyển `products_detail.xlsx` (2 sheet: `products` dạng bảng rộng, `specs`
dạng long-format product_id/spec_key/spec_value) thành 1 file JSON duy nhất
`backend_py/data/products_detail.json`, giữ NGUYÊN tên field thô tiếng Việt
(không map/parse gì ở bước này — việc map sang field canonical + parse
theo `schemas/dmx_registry.json` thuộc về production loader
`app/catalog/load_dmx_catalog.py`, không phải script này).

Chạy:
    python scripts/build_products_detail_json.py \
        --input /path/to/products_detail.xlsx \
        --output backend_py/data/products_detail.json

KHÔNG import script này từ `app/` — production KHÔNG được gọi pd.read_excel.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

TOP_LEVEL_COLUMNS = [
    "product_id",
    "tên sản phẩm",
    "category_name",
    "category_id",
    "brand",
    "Giá gốc",
    "Giá khuyến mãi",
    "rating_vote",
    "quantity_sold",
    "màu sắc",
    "productcode",
    "producttype",
    "onlineSaleOnly",
    "Phụ kiện đi kèm",
    "chính sách bảo hành",
    "promotion",
    "outstanding",
    "url",
    "url_image",
]


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def build_products_detail_json(input_xlsx: Path, output_json: Path) -> int:
    xls = pd.ExcelFile(input_xlsx)
    products_df = pd.read_excel(xls, sheet_name="products")
    specs_df = pd.read_excel(xls, sheet_name="specs")

    # Gom specs long-format thành dict {spec_key: spec_value} theo product_id
    specs_by_product: dict[int, dict[str, str]] = {}
    for spec_row in specs_df.to_dict(orient="records"):
        pid = spec_row["product_id"]
        specs_by_product.setdefault(pid, {})[str(spec_row["spec_key"])] = _clean(spec_row["spec_value"])

    records = []
    for row_dict in products_df.to_dict(orient="records"):
        record = {col: _clean(row_dict.get(col)) for col in TOP_LEVEL_COLUMNS if col in row_dict}
        record["specs"] = specs_by_product.get(row_dict["product_id"], {})
        records.append(record)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    count = build_products_detail_json(args.input, args.output)
    print(f"Đã ghi {count} sản phẩm vào {args.output}")


if __name__ == "__main__":
    main()
