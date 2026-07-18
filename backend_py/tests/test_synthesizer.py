from __future__ import annotations

import json
from types import SimpleNamespace

from app.explanation.synthesizer import generate_explanation
from app.ranking.rank_products import RankingResult

RANKING_OK = RankingResult(
    status="ok",
    results=[
        {
            "product_id": "AC-1",
            "model_code": "AC-1",
            "effective_price": 12_000_000,
            "total_score": 88,
            "matched_reasons": [],
            "tradeoffs": [],
            "missing_data": [],
            "source": {"category": "air_conditioner", "brand": "Samsung", "spec": {"area_min_m2": 15, "area_max_m2": 20}},
        }
    ],
)
STATE = SimpleNamespace(slots={"budget_max": 20_000_000, "room_area_m2": 18})


def test_not_ready_skips_llm_call(scripted_llm):
    llm = scripted_llm("{}")
    result = generate_explanation(RankingResult(status="not_ready", missing_slots=["budget_max"]), STATE, llm=llm)
    assert result.status == "not_ready"


def test_no_results_skips_llm_call(scripted_llm):
    llm = scripted_llm("{}")
    result = generate_explanation(RankingResult(status="no_results", message="Chưa có dữ liệu."), STATE, llm=llm)
    assert result.status == "no_results"


def test_valid_json_wrapped_in_markdown_fence_is_parsed(scripted_llm):
    payload = {
        "summary": "Tóm tắt.",
        "items": [{"product_id": "AC-1", "headline": "Phù hợp ngân sách.", "pros": [], "cons": [], "recommendation_reason": "OK"}],
    }
    wrapped = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    result = generate_explanation(RANKING_OK, STATE, llm=scripted_llm(wrapped))
    assert result.status == "ok"
    assert result.items[0]["product_id"] == "AC-1"


def test_invalid_json_from_llm_gives_parse_error_not_crash(scripted_llm):
    result = generate_explanation(RANKING_OK, STATE, llm=scripted_llm("không phải JSON đâu"))
    assert result.status == "llm_parse_error"
    assert result.error


def test_echoing_llm_end_to_end_success(echoing_llm):
    result = generate_explanation(RANKING_OK, STATE, llm=echoing_llm)
    assert result.status == "ok"
    assert result.items[0]["product_id"] == "AC-1"
    assert result.items[0]["effective_price"] == 12_000_000
