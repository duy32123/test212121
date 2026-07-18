"""
catalog/catalog_store.py — cache catalog production, chỉ dùng DMX JSON.

Đây là điểm truy cập catalog DUY NHẤT cho pipeline (retrieval/ranking/
explanation). KHÔNG import gì từ `load_catalog.py` (Excel, legacy) ở đây.
"""
from __future__ import annotations

from app.catalog.load_dmx_catalog import load_catalog_from_json
from app.config.settings import PRODUCTS_DETAIL_JSON_PATH

_cache: dict[str, dict] = {}


def get_catalog(json_path=None):
    path = str(json_path or PRODUCTS_DETAIL_JSON_PATH)
    if path not in _cache:
        _cache[path] = load_catalog_from_json(path)
    return _cache[path]


def clear_catalog_cache():
    _cache.clear()
