from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.conversation.state import ConversationState
from app.explanation.synthesizer import ExplanationResult, generate_explanation
from app.ranking.rank_products import RankingResult, rank_products
from app.retrieval.filter_products import FilterResult
from app.retrieval.retrieve_for_state import retrieve_for_state


@dataclass
class AdviceResult:
    status: str
    summary: str = ""
    items: list[dict] = None
    corrections: list[dict] = None
    rejected_items: list[dict] = None
    message: str | None = None
    missing_slots: list[str] = None
    retrieval: FilterResult | None = None
    ranking: RankingResult | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("retrieval", None)
        d.pop("ranking", None)
        return d


def build_local_explanation(ranking: RankingResult, state) -> ExplanationResult:
    """Tạo lời giải thích từ matched_reasons + tradeoffs đã có sẵn trong
    ranking results — KHÔNG gọi LLM. Dùng làm fallback khi FPT chậm/lỗi
    hoặc khi budget LLM call đã hết (deterministic NLU đã dùng)."""
    items = []
    for r in ranking.results:
        reasons = r.get("matched_reasons") or []
        tradeoffs = r.get("tradeoffs") or []
        price = r.get("effective_price")
        price_text = f"Giá {round(price / 1_000_000, 1)} triệu." if price else ""

        headline = reasons[0] if reasons else price_text or "Phù hợp tiêu chí lọc."
        pros = reasons[:2] if reasons else (["Nằm trong kết quả lọc phù hợp."] if not reasons else [])
        cons = tradeoffs[:1] if tradeoffs else []

        items.append({
            "product_id": r.get("product_id"),
            "model_code": r.get("model_code"),
            "name": r.get("name"),
            "brand": r.get("brand"),
            "image": r.get("image"),
            "url": r.get("url"),
            "effective_price": price,
            "headline": headline,
            "pros": pros,
            "cons": cons,
            "recommendation_reason": price_text or "Phù hợp tiêu chí đã chọn.",
            "matched_reasons": reasons,
            "tradeoffs": tradeoffs,
            "missing_data": r.get("missing_data") or [],
            "data_source": {"product_id": r.get("product_id"), "model_code": r.get("model_code"), "url": r.get("url")},
            "llm_explanation_missing": True,
        })

    summary = "Dưới đây là các sản phẩm phù hợp nhất dựa trên dữ liệu thật (chưa qua AI diễn giải):"
    return ExplanationResult(
        status="ok",
        summary=summary,
        items=items,
    )


def advise_for_state(
    state: ConversationState,
    llm: Any = None,
    catalog_override: dict | None = None,
    top_n: int = 3,
    skip_llm: bool = False,
) -> AdviceResult:
    """
    Orchestrator toàn pipeline (M2 -> M3 -> M4). `llm` là instance LLM của
    llama_index — bắt buộc truyền tường minh (production: get_default_llm(),
    test: MockLLM). Nếu retrieval/ranking chưa sẵn sàng hoặc không có kết
    quả, KHÔNG gọi LLM — tránh tốn API call vô ích.

    `skip_llm=True`: dùng build_local_explanation() thay vì gọi LLM (khi
    NLU đã dùng deterministic fallback hoặc FPT timeout).
    """
    retrieval = retrieve_for_state(state, catalog_override)
    ranking = rank_products(retrieval, state, top_n=top_n)

    if ranking.status in ("not_ready", "no_results"):
        return AdviceResult(
            status=ranking.status,
            message=ranking.message,
            missing_slots=ranking.missing_slots,
            items=[],
            corrections=[],
            rejected_items=[],
            retrieval=retrieval,
            ranking=ranking,
        )

    if skip_llm:
        explanation = build_local_explanation(ranking, state)
    else:
        explanation = generate_explanation(ranking, state, llm=llm)
        if explanation.status in ("llm_error", "llm_parse_error"):
            # FPT chậm/lỗi/timeout/JSON sai -> lập tức fallback từ dữ liệu
            # thật (matched_reasons/tradeoffs), KHÔNG gọi lại LLM lần 2 —
            # tôn trọng giới hạn "tối đa 1 lần gọi FPT mỗi request".
            explanation = build_local_explanation(ranking, state)

    return AdviceResult(
        status=explanation.status,
        summary=explanation.summary,
        items=explanation.items,
        corrections=explanation.corrections,
        rejected_items=explanation.rejected_items,
        message=explanation.message,
        missing_slots=[],
        retrieval=retrieval,
        ranking=ranking,
    )

