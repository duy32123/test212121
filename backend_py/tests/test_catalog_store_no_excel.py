from __future__ import annotations

import sys

import pytest

from app.catalog.catalog_store import clear_catalog_cache, get_catalog


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_catalog_cache()
    yield
    clear_catalog_cache()


def test_get_catalog_never_calls_pandas_read_excel(monkeypatch):
    """Production catalog_store.get_catalog() KHÔNG được gọi pd.read_excel
    dưới bất kỳ hình thức nào — patch nó để raise nếu lỡ bị gọi."""
    import pandas as pd

    def _boom(*args, **kwargs):
        raise AssertionError("pd.read_excel() KHÔNG được gọi trong đường production (catalog_store.get_catalog)")

    monkeypatch.setattr(pd, "read_excel", _boom)

    catalog = get_catalog()  # nếu code lỡ còn gọi Excel, dòng trên sẽ raise AssertionError
    assert len(catalog) > 100


def test_catalog_store_module_does_not_import_load_catalog_excel_module():
    """catalog_store.py không được import module Excel legacy (load_catalog.py)."""
    import app.catalog.catalog_store as catalog_store_module

    assert not hasattr(catalog_store_module, "load_catalog_from_excel")


def test_all_products_across_catalog_have_dmx_json_source():
    catalog = get_catalog()
    checked = 0
    for products in catalog.values():
        for p in products:
            assert p["source"]["type"] == "dmx_json"
            checked += 1
    assert checked > 10000  # sanity: catalog thật có > 10k sản phẩm
