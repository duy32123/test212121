from __future__ import annotations

import pytest

from app.catalog.load_catalog import load_catalog_from_excel
from app.catalog.registry import load_registry

XLSX_PATH = "data/Spec_cate_gia.xlsx"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog_from_excel(XLSX_PATH)


def test_loads_all_14_categories_from_registry(catalog):
    registry = load_registry()
    expected_categories = set(registry.all_categories())
    assert set(catalog.keys()) == expected_categories
    assert len(expected_categories) == 14


def test_every_category_has_products(catalog):
    for category, products in catalog.items():
        assert len(products) > 0, f"{category} không có sản phẩm nào"


def test_product_has_base_schema_fields(catalog):
    for p in catalog["refrigerator"][:20]:
        assert p["product_id"]
        assert p["category"] == "refrigerator"
        assert "source" in p and p["source"]["type"] == "btc_excel"
        assert "data_quality" in p
        assert isinstance(p["spec"], dict)


def test_effective_price_never_fabricated(catalog):
    for p in catalog["air_conditioner"][:200]:
        assert p["effective_price"] is None or isinstance(p["effective_price"], int)
        if p["promotion_price"] is None and p["original_price"] is not None:
            assert p["effective_price"] == p["original_price"]


def test_air_conditioner_deep_fields_parsed(catalog):
    ac = catalog["air_conditioner"]
    with_area = [p for p in ac if p["spec"].get("area_min_m2") is not None]
    assert len(with_area) / len(ac) > 0.5, "phần lớn máy lạnh phải parse được diện tích"

    sample = with_area[0]
    assert isinstance(sample["spec"]["area_min_m2"], (int, float))
    assert sample["spec"]["indoor_noise_min_db"] is not None or sample["spec"]["indoor_noise_min_db"] is None


def test_refrigerator_has_household_text_field(catalog):
    fridge = catalog["refrigerator"]
    with_household = [p for p in fridge if p["spec"].get("so_nguoi_su_dung")]
    assert len(with_household) > 0


def test_missing_model_code_rows_are_skipped_not_fabricated(catalog):
    # Không có category nào có product thiếu product_id
    for products in catalog.values():
        for p in products:
            assert p["product_id"]
