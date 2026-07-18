"""
explanation/synthesizer.py — dùng llama_index THẬT để tạo lời giải thích
cho Top N (RAG trên context đã lọc sẵn bằng code, không semantic search
trên toàn bộ catalog), sau đó chạy qua Guardrails AI THẬT để validate/sửa.

Đây là nơi 2 thư viện người dùng yêu cầu (llama_index, guardrails-ai) được
áp dụng thật — không phải code tự viết mô phỏng lại.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable

from llama_index.core import get_response_synthesizer

from app.config.settings import FPT_TIMEOUT_SECONDS
from app.explanation.nodes import build_nodes_with_scores
from app.explanation.prompt import EXPLANATION_QA_TEMPLATE
from app.guardrail.guard import build_guard_for_ranking

QUERY_TEXT = "Hãy giải thích và so sánh các sản phẩm phù hợp nhất với nhu cầu khách hàng."

# 1 thread dùng chung cho các lời gọi LLM đồng bộ (llama_index synthesize là
# hàm blocking) — cho phép áp đặt hard timeout ở tầng ứng dụng, độc lập với
# timeout của HTTP client bên trong provider (phòng khi provider không tôn
# trọng đúng timeout đã cấu hình).
_LLM_CALL_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm-call")


def _synthesize_with_hard_timeout(synthesizer, query: str, nodes, timeout_seconds: float):
    future = _LLM_CALL_EXECUTOR.submit(synthesizer.synthesize, query, nodes=nodes)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        raise TimeoutError(f"LLM không phản hồi trong {timeout_seconds}s (hard timeout tầng ứng dụng).") from exc


def _parse_json_from_llm_text(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ValueError("LLM không trả về text hợp lệ.")
    stripped = text.strip()
    stripped = re.sub(r"^```json\s*", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"^```\s*", "", stripped)
    stripped = re.sub(r"```\s*$", "", stripped)
    try:
        return json.loads(stripped.strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Không parse được JSON từ output LLM: {exc}") from exc


@dataclass
class ExplanationResult:
    status: str  # "not_ready" | "no_results" | "ok" | "corrected" | "blocked" | "llm_error" | "llm_parse_error"
    summary: str = ""
    items: list[dict] = field(default_factory=list)
    corrections: list[dict] = field(default_factory=list)
    rejected_items: list[dict] = field(default_factory=list)
    message: str | None = None
    error: str | None = None
    raw_text: str | None = None
    source_node_ids: list[str] = field(default_factory=list)


def generate_explanation(
    ranking, state, llm: Any = None, response_mode: str = "compact", timeout_seconds: float | None = None
) -> ExplanationResult:
    """
    ranking: RankingResult (app.ranking.rank_products)
    state:   ConversationState
    llm:     llama_index LLM instance (bắt buộc truyền tường minh — production
             dùng Anthropic thật đọc API key từ .env qua app/explanation/llm_factory.py,
             test dùng MockLLM/FakeLLM của llama_index để không gọi mạng).
    timeout_seconds: hard timeout tầng ứng dụng cho lời gọi LLM (mặc định
             FPT_TIMEOUT_SECONDS từ .env, ~3s) — độc lập với timeout đã cấu
             hình sẵn trên chính LLM client (xem llm_factory.py), đảm bảo
             generate_explanation() không bao giờ treo quá thời gian này dù
             provider có tôn trọng đúng timeout của nó hay không.
    """
    if ranking is None or ranking.status == "not_ready":
        return ExplanationResult(status="not_ready", message=None)

    if ranking.status == "no_results" or not ranking.results:
        return ExplanationResult(status="no_results", message=ranking.message or "Không có sản phẩm để giải thích.")

    if llm is None:
        raise ValueError(
            "generate_explanation() cần truyền llm tường minh (llama_index LLM instance). "
            "Production dùng app.explanation.llm_factory.get_default_llm(); test dùng MockLLM giả lập."
        )

    nodes = build_nodes_with_scores(ranking.results)
    synthesizer = get_response_synthesizer(
        llm=llm, response_mode=response_mode, text_qa_template=EXPLANATION_QA_TEMPLATE, streaming=False
    )

    effective_timeout = timeout_seconds if timeout_seconds is not None else FPT_TIMEOUT_SECONDS

    try:
        response = _synthesize_with_hard_timeout(synthesizer, QUERY_TEXT, nodes, effective_timeout)
    except Exception as exc:  # noqa: BLE001 — lỗi mạng/API key/timeout đều rơi vào đây
        return ExplanationResult(status="llm_error", error=str(exc))

    try:
        parsed = _parse_json_from_llm_text(response.response)
    except ValueError as exc:
        return ExplanationResult(status="llm_parse_error", error=str(exc), raw_text=response.response)

    bundle = build_guard_for_ranking(ranking.results, state.slots)
    outcome = bundle.guard.parse(json.dumps(parsed, ensure_ascii=False), metadata=bundle.metadata)

    items = outcome.validated_output.get("items", []) if outcome.validated_output else []
    corrections = bundle.metadata.get("_corrections", [])
    rejected_items = bundle.metadata.get("_rejected_items", [])

    all_missing = items and all(i.get("llm_explanation_missing") for i in items)
    status = "blocked" if all_missing or not items else ("corrected" if corrections or rejected_items else "ok")

    return ExplanationResult(
        status=status,
        summary=(outcome.validated_output or {}).get("summary", "") if outcome.validated_output else "",
        items=items,
        corrections=corrections,
        rejected_items=rejected_items,
        message="Không có nội dung giải thích hợp lệ từ LLM sau khi kiểm tra guardrail." if status == "blocked" else None,
        source_node_ids=[n.node.node_id for n in getattr(response, "source_nodes", [])],
    )
