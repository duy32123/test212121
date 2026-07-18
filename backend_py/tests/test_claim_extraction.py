from __future__ import annotations

from app.guardrail.claim_extraction import SpecMention, extract_money_mentions, extract_spec_mentions


def test_extract_money_million_words():
    assert extract_money_mentions("Giá khoảng 20 triệu, khá hợp lý") == [20_000_000]


def test_extract_money_thousand_separator():
    assert extract_money_mentions("Giá niêm yết 14.990.000đ") == [14_990_000]


def test_extract_money_multiple_mentions():
    mentions = extract_money_mentions("Rẻ hơn 3 triệu so với model 20 triệu kia")
    assert 3_000_000 in mentions and 20_000_000 in mentions


def test_extract_money_none_found():
    assert extract_money_mentions("Sản phẩm chạy êm, tiết kiệm điện") == []


def test_extract_money_non_string_input():
    assert extract_money_mentions(None) == []


def test_extract_spec_mentions_multiple_units():
    mentions = extract_spec_mentions("Phù hợp phòng 18m², chạy êm 29 dB, phù hợp gia đình 4 người")
    assert SpecMention(18, "m²") in mentions
    assert SpecMention(29, "dB") in mentions
    assert SpecMention(4, "người") in mentions


def test_extract_spec_mentions_liters():
    assert extract_spec_mentions("Dung tích 313 lít, đủ dùng cho gia đình đông người") == [SpecMention(313, "lít")]


def test_extract_spec_mentions_none_found():
    assert extract_spec_mentions("Thiết kế đẹp, màu sắc hiện đại") == []
