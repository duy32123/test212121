from __future__ import annotations

from app.catalog.parse_specs import (
    Range,
    effective_price,
    parse_boolean_vn,
    parse_efficiency_index,
    parse_inverter,
    parse_noise_reading,
    parse_number,
    parse_range_generic,
    parse_star_rating,
    parse_year,
)


def test_parse_range_generic_two_number_range():
    assert parse_range_generic("Từ 30 - 40m² (từ 80 đến 120m³)") == Range(30, 40)


def test_parse_range_generic_below():
    assert parse_range_generic("Dưới 15m² (từ 30 đến 45m³)") == Range(0, 15)


def test_parse_range_generic_above():
    assert parse_range_generic("Trên 5 người") == Range(5, None)


def test_parse_range_generic_simple_range():
    assert parse_range_generic("3 - 4 người") == Range(3, 4)


def test_parse_range_generic_single_number():
    assert parse_range_generic("2 cánh") == Range(2, 2)


def test_parse_range_generic_no_data():
    assert parse_range_generic("Không") is None
    assert parse_range_generic("Đang cập nhật") is None
    assert parse_range_generic(None) is None


def test_parse_number_vietnamese_thousand_separator():
    assert parse_number("9.000 BTU") == 9000.0
    assert parse_number("17.400 BTU") == 17400.0


def test_parse_number_no_data():
    assert parse_number("Không") is None


def test_parse_noise_reading_with_markers():
    r = parse_noise_reading("Dàn lạnh: 45/34/29 dB - Dàn nóng: 51 dB")
    assert r.indoor_min_db == 29
    assert r.indoor_max_db == 45
    assert r.outdoor_db == 51


def test_parse_noise_reading_no_data():
    r = parse_noise_reading("Không")
    assert r.indoor_min_db is None and r.outdoor_db is None


def test_parse_star_rating_and_efficiency_index():
    text = "5 sao (Hiệu suất năng lượng 6.23)"
    assert parse_star_rating(text) == 5
    assert parse_efficiency_index(text) == 6.23


def test_parse_inverter():
    assert parse_inverter("Máy lạnh Inverter") is True
    assert parse_inverter("Máy lạnh không Inverter") is False
    assert parse_inverter("Không") is None


def test_parse_year():
    assert parse_year("2026") == 2026
    assert parse_year("Không") is None


def test_parse_boolean_vn():
    assert parse_boolean_vn("Có") is True
    assert parse_boolean_vn("Không") is False
    assert parse_boolean_vn("gì đó khác") is None


def test_effective_price_prefers_promotion():
    assert effective_price(20_000_000, 18_500_000) == 18_500_000


def test_effective_price_fallback_original():
    assert effective_price(20_000_000, None) == 20_000_000


def test_effective_price_missing_both():
    assert effective_price(None, None) is None


def test_range_contains():
    assert Range(15, 20).contains(18) is True
    assert Range(15, 20).contains(25) is False
    assert Range(5, None).contains(100) is True


from app.catalog.parse_specs import parse_btu, parse_quantity_sold, price_to_int, slugify_category_name


def test_parse_btu_ignores_leading_hp_number():
    assert parse_btu("2.5 HP - 24000 BTU") == 24000
    assert parse_btu("2 HP - 18.500 BTU") == 18500


def test_parse_btu_no_data():
    assert parse_btu("Không") is None
    assert parse_btu("2.5 HP") is None  # không có BTU trong chuỗi


def test_parse_quantity_sold_with_k_suffix():
    assert parse_quantity_sold("14,5k") == 14500
    assert parse_quantity_sold("9k") == 9000


def test_parse_quantity_sold_plain_number():
    assert parse_quantity_sold("292") == 292


def test_parse_quantity_sold_no_data():
    assert parse_quantity_sold(None) is None


def test_price_to_int_from_number():
    assert price_to_int(390000) == 390000


def test_price_to_int_no_data():
    assert price_to_int(None) is None


def test_slugify_category_name_vietnamese():
    assert slugify_category_name("Tủ lạnh") == "tu_lanh"
    assert slugify_category_name("Tủ mát, tủ đông") == "tu_mat_tu_dong"
    assert slugify_category_name("Máy lạnh") == "may_lanh"


def test_slugify_category_name_empty():
    assert slugify_category_name("") == "unknown_category"
    assert slugify_category_name("!!!") == "unknown_category"
