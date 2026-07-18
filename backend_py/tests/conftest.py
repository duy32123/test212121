from __future__ import annotations

import json
import os

# Ép dùng MemorySessionStore cho toàn bộ test (nhanh, cô lập, không ghi
# sessions.db thật) — PHẢI set trước khi bất kỳ test module nào import
# app.server (nơi session store được dựng 1 lần ở module scope).
os.environ.setdefault("SESSION_STORE", "memory")

import pytest
from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
from llama_index.core.llms.callbacks import llm_completion_callback


class ScriptedLLM(CustomLLM):
    """LLM giả lập cho test — trả về đúng text đã cấu hình trước, không gọi mạng."""

    response_text: str = "{}"

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(context_window=8192, num_output=2048)

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        return CompletionResponse(text=self.response_text)

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs):
        raise NotImplementedError("Không dùng streaming trong test.")


def make_scripted_llm(response_text: str) -> ScriptedLLM:
    return ScriptedLLM(response_text=response_text)


class EchoingLLM(CustomLLM):
    """LLM giả lập 'trung thực' — đọc context (product_id + effective_price)
    trong prompt và tự sinh JSON đúng schema, dùng cho test tích hợp thành công."""

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(context_window=8192, num_output=2048)

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        import re

        price_matches = re.findall(r'"product_id":\s*"([^"]+)"[^}]*?"effective_price":\s*(\d+)', prompt)
        prices = dict(price_matches)
        items = [
            {
                "product_id": pid,
                "headline": f"Giá {round(int(price) / 1_000_000)} triệu.",
                "pros": ["Phù hợp nhu cầu đã nêu."],
                "cons": [],
                "recommendation_reason": "Khớp với ngân sách và nhu cầu khách yêu cầu.",
            }
            for pid, price in prices.items()
        ]
        return CompletionResponse(text=json.dumps({"summary": "Gợi ý phù hợp nhất.", "items": items}, ensure_ascii=False))

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs):
        raise NotImplementedError


@pytest.fixture
def scripted_llm():
    return make_scripted_llm


@pytest.fixture
def echoing_llm():
    return EchoingLLM()


class CountingLLM(CustomLLM):
    """LLM giả lập đếm số lần được gọi — dùng để xác nhận 'tối đa 1 lần
    gọi FPT mỗi request'. `response_text` cấu hình được để mô phỏng cả
    NLU JSON lẫn explanation JSON."""

    response_text: str = "{}"
    call_count: int = 0

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(context_window=8192, num_output=2048)

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        self.call_count += 1
        return CompletionResponse(text=self.response_text)

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs):
        raise NotImplementedError


class SlowLLM(CustomLLM):
    """LLM giả lập 'FPT bị treo' — sleep lâu hơn timeout cấu hình, dùng để
    kiểm tra hard-timeout tầng ứng dụng (không phụ thuộc mạng thật)."""

    sleep_seconds: float = 10.0
    call_count: int = 0

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(context_window=8192, num_output=2048)

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        import time

        self.call_count += 1
        time.sleep(self.sleep_seconds)
        return CompletionResponse(text="{}")

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs):
        raise NotImplementedError


@pytest.fixture
def counting_llm():
    return CountingLLM


@pytest.fixture
def slow_llm():
    return SlowLLM
