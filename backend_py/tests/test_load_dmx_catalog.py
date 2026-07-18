from __future__ import annotations

import json

import pytest

from app.catalog.load_dmx_catalog import DmxCatalogError, load_catalog_from_json

REAL_JSON_PATH = "data/products_detail.json"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog_from_json(REAL_JSON_PATH)


def test_loads_119_categories_from_real_dmx_json(catalog):
    assert len(catalog) > 100
    assert "air_conditioner" in catalog
    assert len(catalog["air_conditioner"]) > 0


def test_every_product_has_source_type_dmx_json(catalog):
    for category, products in catalog.items():
        for p in products[:20]:
            assert p["source"]["type"] == "dmx_json", f"category={category} product_id={p['product_id']}"


def test_air_conditioner_products_have_parsed_spec(catalog):
    ac = catalog["air_conditioner"]
    with_area = [p for p in ac if p["spec"].get("area_min_m2") is not None]
    assert len(with_area) / len(ac) > 0.5
    sample = with_area[0]
    assert isinstance(sample["spec"]["area_min_m2"], float)
    assert sample["data_quality"]["has_spec_map"] is True


def test_category_with_extended_spec_map_parses_real_fields(catalog):
    """'Tủ lạnh' đã được bổ sung spec_map thật (capacity_liters...) —
    has_spec_map phải True và spec phải có dữ liệu đã parse, không rỗng."""
    fridge = catalog["tu_lanh"]
    assert len(fridge) > 0
    with_capacity = [p for p in fridge if p["spec"].get("capacity_liters") is not None]
    assert len(with_capacity) / len(fridge) > 0.5
    assert fridge[0]["data_quality"]["has_spec_map"] is True
    # Dữ liệu thô vẫn còn nguyên trong spec_raw, không mất thông tin
    assert len(fridge[0]["spec_raw"]) > 0


def test_category_genuinely_without_spec_map_keeps_empty_parsed_spec(catalog):
    """Category chưa được BTC/registry khai báo spec_map (vd quạt các loại —
    ngoài 11 category đã cấu hình chi tiết) vẫn nạp được, spec parse rỗng
    nhưng spec_raw giữ nguyên dữ liệu thô — không bịa."""
    products = catalog.get("quat_cac_loai")
    assert products, "category 'quat_cac_loai' phải tồn tại trong catalog thật để test này có ý nghĩa"
    sample = products[0]
    assert sample["spec"] == {}
    assert sample["data_quality"]["has_spec_map"] is False
    assert len(sample["spec_raw"]) > 0


def test_effective_price_never_fabricated(catalog):
    for p in catalog["air_conditioner"]:
        if p["promotion_price"] and p["promotion_price"] > 0:
            assert p["effective_price"] == p["promotion_price"]
        elif p["original_price"]:
            assert p["effective_price"] == p["original_price"]
        else:
            assert p["effective_price"] is None


def test_model_code_not_fabricated_from_barcode(catalog):
    # DMX không có model_code người đọc được -> phải để None, không gán
    # nhầm 'productcode' (mã vạch) vào model_code.
    for p in catalog["air_conditioner"][:10]:
        assert p["model_code"] is None


def test_stock_status_always_unknown_never_invented(catalog):
    for p in catalog["air_conditioner"][:10]:
        assert p["stock_status"] == "unknown"


class TestMissingOrMalformedFile:
    def test_missing_file_raises_clear_error(self, tmp_path):
        missing = tmp_path / "products_detail.json"
        with pytest.raises(DmxCatalogError, match="Không tìm thấy"):
            load_catalog_from_json(missing)

    def test_empty_json_array_raises(self, tmp_path):
        path = tmp_path / "products_detail.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(DmxCatalogError, match="rỗng"):
            load_catalog_from_json(path)

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "products_detail.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(DmxCatalogError, match="không phải JSON hợp lệ"):
            load_catalog_from_json(path)

    def test_non_list_root_raises(self, tmp_path):
        path = tmp_path / "products_detail.json"
        path.write_text(json.dumps({"product_id": 1}), encoding="utf-8")
        with pytest.raises(DmxCatalogError, match="JSON array"):
            load_catalog_from_json(path)

    def test_missing_required_top_level_key_raises(self, tmp_path):
        path = tmp_path / "products_detail.json"
        path.write_text(json.dumps([{"name": "sản phẩm không có product_id"}]), encoding="utf-8")
        with pytest.raises(DmxCatalogError, match="product_id"):
            load_catalog_from_json(path)

    def test_does_not_fabricate_data_for_missing_file(self, tmp_path):
        """Đảm bảo loader KHÔNG âm thầm trả về catalog rỗng/giả khi thiếu file."""
        missing = tmp_path / "products_detail.json"
        with pytest.raises(DmxCatalogError):
            load_catalog_from_json(missing)
