"""
explanation/nodes.py — chuyển mỗi sản phẩm trong Top N (đã lọc + rank ở
Module 2/3) thành 1 `TextNode` của llama_index. Đây là nơi dùng llama_index
thật cho việc RETRIEVAL-AUGMENTED GENERATION: các node này đóng vai trò
"context nguồn" cho LLM, và llama_index tự động trả kèm `source_nodes`
trong response — cho phép Module 4 truy vết node nào sinh ra câu trả lời
nào (citation), khớp đúng tinh thần RAG dùng cho dữ liệu ĐÃ ĐƯỢC LỌC SẴN
bằng code (không phải semantic search trên toàn bộ catalog).
"""
from __future__ import annotations

import json
from typing import Any

from llama_index.core.schema import NodeWithScore, TextNode

_CATEGORY_KEY_SPEC_FIELDS = {
    "air_conditioner": [
        "area_min_m2",
        "area_max_m2",
        "indoor_noise_min_db",
        "indoor_noise_max_db",
        "outdoor_noise_db",
        "energy_stars",
        "cspf",
        "inverter",
        "energy_saving_technology",
    ],
}
_DEFAULT_KEY_SPEC_LIMIT = 8


def _pick_key_specs(source: dict[str, Any]) -> dict[str, Any]:
    category = source.get("category")
    spec = source.get("spec", {})
    keys = _CATEGORY_KEY_SPEC_FIELDS.get(category)
    if keys:
        return {k: spec.get(k) for k in keys}
    # Category chưa có danh sách field ưu tiên riêng -> lấy vài field đầu có giá trị
    picked = {}
    for k, v in spec.items():
        if v not in (None, [], ""):
            picked[k] = v
        if len(picked) >= _DEFAULT_KEY_SPEC_LIMIT:
            break
    return picked


def ranked_item_to_node(ranked_item: dict[str, Any]) -> TextNode:
    source = ranked_item.get("source", {})
    payload = {
        "product_id": ranked_item["product_id"],
        "model_code": ranked_item.get("model_code"),
        "name": source.get("name"),
        "brand": source.get("brand"),
        "effective_price": ranked_item.get("effective_price"),
        "total_score": ranked_item.get("total_score"),
        "key_specs": _pick_key_specs(source),
        "matched_reasons": ranked_item.get("matched_reasons", []),
        "tradeoffs": ranked_item.get("tradeoffs", []),
        "missing_data": ranked_item.get("missing_data", []),
    }
    text = json.dumps(payload, ensure_ascii=False)
    return TextNode(text=text, metadata={"product_id": ranked_item["product_id"]})


def build_nodes_with_scores(ranking_results: list[dict[str, Any]]) -> list[NodeWithScore]:
    return [
        NodeWithScore(node=ranked_item_to_node(item), score=item.get("total_score", 0) / 100)
        for item in ranking_results
    ]
