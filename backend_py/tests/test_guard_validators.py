from __future__ import annotations

import json

from app.guardrail.guard import build_guard_for_ranking
from app.guardrail.validators import FALLBACK_TEXT


def ranked(id_, price, area_min=None, area_max=None, noise_min=None, noise_max=None):
    return {
        "product_id": id_,
        "model_code": id_,
        "effective_price": price,
        "matched_reasons": ["Phù hợp ngân sách."],
        "tradeoffs": [],
        "missing_data": [],
        "source": {
            "category": "air_conditioner",
            "spec": {"area_min_m2": area_min, "area_max_m2": area_max, "indoor_noise_min_db": noise_min, "indoor_noise_max_db": noise_max},
        },
    }


RANKING_RESULTS = [
    ranked("AC-1", 12_000_000, 15, 20, 29, 45),
    ranked("AC-2", 15_000_000, 20, 30),
]
STATE_SLOTS = {"budget_max": 20_000_000, "room_area_m2": 18}


def _run_guard(llm_output: dict):
    bundle = build_guard_for_ranking(RANKING_RESULTS, STATE_SLOTS)
    outcome = bundle.guard.parse(json.dumps(llm_output, ensure_ascii=False), metadata=bundle.metadata)
    return outcome, bundle.metadata


def test_valid_claims_pass_through_unchanged():
    llm_output = {
        "summary": "AC-1 phù hợp ngân sách.",
        "items": [
            {
                "product_id": "AC-1",
                "headline": "Giá 12 triệu, chạy êm 29 dB, phù hợp phòng 18m²",
                "pros": ["Phù hợp ngân sách 20 triệu khách đưa ra"],
                "cons": [],
                "recommendation_reason": "Rẻ hơn 3 triệu so với AC-2 mà vẫn đáp ứng đủ nhu cầu.",
            },
            {"product_id": "AC-2", "headline": "Diện tích lớn hơn.", "pros": [], "cons": [], "recommendation_reason": "Phù hợp phòng >20m²."},
        ],
    }
    outcome, metadata = _run_guard(llm_output)
    items = outcome.validated_output["items"]
    item1 = next(i for i in items if i["product_id"] == "AC-1")
    assert item1["headline"] == llm_output["items"][0]["headline"]
    assert item1["effective_price"] == 12_000_000
    assert metadata["_corrections"] == []


def test_unknown_product_id_rejected():
    llm_output = {
        "items": [
            {"product_id": "AC-1", "headline": "OK.", "pros": [], "cons": [], "recommendation_reason": "OK"},
            {"product_id": "AC-BIA-RA", "headline": "Sản phẩm không tồn tại.", "pros": [], "cons": [], "recommendation_reason": "x"},
        ]
    }
    outcome, metadata = _run_guard(llm_output)
    assert any(r["product_id"] == "AC-BIA-RA" for r in metadata["_rejected_items"])
    assert "AC-BIA-RA" not in [i["product_id"] for i in outcome.validated_output["items"]]


def test_fabricated_price_replaced_with_fallback():
    llm_output = {
        "items": [
            {"product_id": "AC-1", "headline": "Giá chỉ 8 triệu, siêu rẻ", "pros": [], "cons": [], "recommendation_reason": "Đáng mua."},
            {"product_id": "AC-2", "headline": "Lựa chọn phù hợp.", "pros": [], "cons": [], "recommendation_reason": "Phù hợp nhu cầu."},
        ]
    }
    outcome, metadata = _run_guard(llm_output)
    item1 = next(i for i in outcome.validated_output["items"] if i["product_id"] == "AC-1")
    assert item1["headline"] == FALLBACK_TEXT
    assert item1["effective_price"] == 12_000_000  # luôn lấy từ nguồn thật
    assert any(c["product_id"] == "AC-1" and c["field"] == "headline" for c in metadata["_corrections"])


def test_fabricated_spec_claim_replaced():
    llm_output = {
        "items": [
            {"product_id": "AC-1", "headline": "Chạy siêu êm chỉ 10 dB", "pros": [], "cons": [], "recommendation_reason": "OK"},
            {"product_id": "AC-2", "headline": "Lựa chọn phù hợp.", "pros": [], "cons": [], "recommendation_reason": "Phù hợp nhu cầu."},
        ]
    }
    outcome, metadata = _run_guard(llm_output)
    item1 = next(i for i in outcome.validated_output["items"] if i["product_id"] == "AC-1")
    assert item1["headline"] == FALLBACK_TEXT
    assert metadata["_corrections"][0]["reason"] == "unverified_numeric_claim"


def test_missing_product_added_back_with_flag():
    llm_output = {"items": [{"product_id": "AC-1", "headline": "OK.", "pros": [], "cons": [], "recommendation_reason": "OK"}]}
    outcome, _ = _run_guard(llm_output)
    items = outcome.validated_output["items"]
    missing_one = next(i for i in items if i["product_id"] == "AC-2")
    assert missing_one.get("llm_explanation_missing") is True
    assert missing_one["effective_price"] == 15_000_000


def test_all_items_unknown_results_in_all_missing_flagged():
    llm_output = {"items": [{"product_id": "GHOST", "headline": "x", "pros": [], "cons": [], "recommendation_reason": "x"}]}
    outcome, metadata = _run_guard(llm_output)
    items = outcome.validated_output["items"]
    assert all(i.get("llm_explanation_missing") for i in items)
    assert len(metadata["_rejected_items"]) == 1
