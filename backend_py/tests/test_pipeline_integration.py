from __future__ import annotations

import json

import pytest
from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
from llama_index.core.llms.callbacks import llm_completion_callback

from app.catalog.load_catalog import load_catalog_from_excel
from app.conversation.state import create_conversation_state
from app.conversation.turn import process_turn
from app.pipeline import advise_for_state

XLSX_PATH = "data/Spec_cate_gia.xlsx"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog_from_excel(XLSX_PATH)


class HallucinatingLLM(CustomLLM):
    """LLM giả lập KHÔNG trung thực — bịa 1 sản phẩm ngoài Top N."""

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(context_window=8192, num_output=1024)

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        payload = {
            "summary": "Tóm tắt.",
            "items": [
                {
                    "product_id": "SAN-PHAM-BIA-RA",
                    "headline": "Giá chỉ 1 triệu, siêu hời!",
                    "pros": [],
                    "cons": [],
                    "recommendation_reason": "x",
                }
            ],
        }
        return CompletionResponse(text=json.dumps(payload, ensure_ascii=False))

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs):
        raise NotImplementedError


def test_full_pipeline_success_with_honest_llm(catalog, echoing_llm):
    state = create_conversation_state("sess_1")
    turn = process_turn(state, {"category": "máy lạnh", "budget": "20 triệu", "area": "18m2", "location": "phòng ngủ"})
    state = turn.state
    assert turn.status == "ready"

    result = advise_for_state(state, llm=echoing_llm, catalog_override=catalog, top_n=3)

    assert result.retrieval.status in ("ok", "relaxed")
    assert result.status in ("ok", "corrected")
    assert len(result.items) > 0
    for item in result.items:
        ranked_source = next(r for r in result.ranking.results if r["product_id"] == item["product_id"])
        assert item["effective_price"] == ranked_source["effective_price"]


def test_full_pipeline_blocks_hallucinated_products(catalog):
    state = create_conversation_state("sess_2")
    turn = process_turn(state, {"category": "máy lạnh", "budget": "20 triệu", "area": "18m2", "location": "phòng ngủ"})
    state = turn.state

    result = advise_for_state(state, llm=HallucinatingLLM(), catalog_override=catalog, top_n=3)

    assert any(r["product_id"] == "SAN-PHAM-BIA-RA" for r in result.rejected_items)
    assert len(result.items) > 0
    assert all(i.get("llm_explanation_missing") for i in result.items)
    assert result.status == "blocked"


def test_unrealistic_budget_gives_no_results_without_calling_llm(catalog):
    state = create_conversation_state("sess_3")
    turn = process_turn(state, {"category": "máy lạnh", "budget": "20 triệu", "area": "18m2", "location": "phòng ngủ"})
    state = turn.state
    state = state.with_updates(slots={**state.slots, "budget_max": 100_000})

    calls = {"count": 0}

    class CountingLLM(CustomLLM):
        @property
        def metadata(self) -> LLMMetadata:
            return LLMMetadata(context_window=1024, num_output=256)

        @llm_completion_callback()
        def complete(self, prompt: str, **kwargs) -> CompletionResponse:
            calls["count"] += 1
            return CompletionResponse(text="{}")

        @llm_completion_callback()
        def stream_complete(self, prompt: str, **kwargs):
            raise NotImplementedError

    result = advise_for_state(state, llm=CountingLLM(), catalog_override=catalog)
    assert result.status == "no_results"
    assert calls["count"] == 0


def test_refrigerator_category_end_to_end(catalog, echoing_llm):
    state = create_conversation_state("sess_4")
    turn = process_turn(state, {"category": "tủ lạnh", "budget": "20 triệu", "household": "4"})
    state = turn.state
    assert turn.status == "ready"

    result = advise_for_state(state, llm=echoing_llm, catalog_override=catalog, top_n=3)
    assert result.status in ("ok", "corrected", "no_results")
    if result.status != "no_results":
        assert all(i["effective_price"] is not None for i in result.items if not i.get("llm_explanation_missing"))
