from __future__ import annotations

import pytest

from app.catalog.dmx_registry import (
    DmxRegistryError,
    apply_spec_field_mapping,
    DmxSpecFieldMapping,
    load_dmx_registry,
)


def test_load_dmx_registry_from_real_schema_file():
    registry = load_dmx_registry()
    assert "product_id" in registry.top_level_mapping
    assert "Máy lạnh" in registry.categories
    assert registry.categories["Máy lạnh"].slug == "air_conditioner"


def test_slug_for_known_category_uses_explicit_slug():
    registry = load_dmx_registry()
    assert registry.slug_for("Máy lạnh") == "air_conditioner"


def test_slug_for_unknown_category_falls_back_to_slugify():
    registry = load_dmx_registry()
    assert registry.slug_for("Tủ lạnh") == "tu_lanh"
    assert registry.slug_for("Máy giặt") == "may_giat"


def test_missing_registry_file_raises_clear_error(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"
    with pytest.raises(DmxRegistryError, match="Không tìm thấy"):
        load_dmx_registry(path=missing_path)


def test_apply_spec_field_mapping_two_field_area():
    mapping = DmxSpecFieldMapping(source_key="Phạm vi làm lạnh hiệu quả", target_keys=["area_min_m2", "area_max_m2"], parser="parse_area")
    result = apply_spec_field_mapping(mapping, "Từ 30 - 40m2 (từ 80 đến 120m3)")
    assert result == {"area_min_m2": 30.0, "area_max_m2": 40.0}


def test_apply_spec_field_mapping_three_field_noise():
    mapping = DmxSpecFieldMapping(
        source_key="Độ ồn trung bình", target_keys=["indoor_noise_min_db", "indoor_noise_max_db", "outdoor_noise_db"], parser="parse_noise"
    )
    result = apply_spec_field_mapping(mapping, "Dàn lạnh: 16/14/12 dB - Dàn nóng: 57 dB")
    assert result == {"indoor_noise_min_db": 12.0, "indoor_noise_max_db": 16.0, "outdoor_noise_db": 57.0}


def test_apply_spec_field_mapping_single_value_btu():
    mapping = DmxSpecFieldMapping(source_key="Công suất làm lạnh", target_keys=["cooling_capacity_btu"], parser="parse_btu")
    result = apply_spec_field_mapping(mapping, "2.5 HP - 24000 BTU")
    assert result == {"cooling_capacity_btu": 24000}


def test_apply_spec_field_mapping_unsupported_parser_raises():
    mapping = DmxSpecFieldMapping(source_key="x", target_keys=["y"], parser="parser_khong_ton_tai")
    with pytest.raises(DmxRegistryError, match="không được hỗ trợ"):
        apply_spec_field_mapping(mapping, "abc")
