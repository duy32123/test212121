from __future__ import annotations

from functools import lru_cache

from app.config.settings import FPT_TIMEOUT_SECONDS, LLM_BASE_URL, LLM_MAX_TOKENS, LLM_MODEL, LLM_PROVIDER, require_llm_api_key


@lru_cache(maxsize=1)
def get_default_llm():
    """
    LLM thật cho production — đọc config từ backend_py/.env, không hardcode
    key/provider nào trong code. Chọn provider qua biến LLM_PROVIDER:

      LLM_PROVIDER=anthropic (mặc định) -> llama-index-llms-anthropic
      LLM_PROVIDER=deepseek             -> llama-index-llms-deepseek
                                            (LLM_BASE_URL tuỳ chọn, mặc định
                                            https://api.deepseek.com)
      LLM_PROVIDER=openai_like          -> llama-index-llms-openai-like,
                                            dùng cho BẤT KỲ API nào tương
                                            thích chuẩn OpenAI chat completions
                                            (bắt buộc phải điền LLM_BASE_URL) —
                                            đây là đường FPT-AI dùng.

    `timeout=FPT_TIMEOUT_SECONDS` (mặc định 3s) và `max_tokens=LLM_MAX_TOKENS`
    (mặc định 600) áp dụng cho CẢ 3 provider — đảm bảo lời gọi LLM không kéo
    dài quá ngân sách thời gian của request (yêu cầu phản hồi < 5s).

    `@lru_cache(maxsize=1)`: LLM client (kết nối HTTP, cấu hình...) được
    dựng đúng 1 LẦN và tái sử dụng cho mọi request — tránh overhead khởi tạo
    lại mỗi request. Được warm-up sẵn khi server khởi động (xem server.py).

    Raise rõ ràng nếu thiếu key/base_url, không âm thầm dùng giá trị rỗng.
    Trong test, KHÔNG gọi hàm này — dùng CustomLLM/MockLLM của llama_index.
    """
    api_key = require_llm_api_key()

    if LLM_PROVIDER == "anthropic":
        from llama_index.llms.anthropic import Anthropic

        kwargs = {"model": LLM_MODEL, "api_key": api_key, "max_tokens": LLM_MAX_TOKENS, "timeout": FPT_TIMEOUT_SECONDS}
        if LLM_BASE_URL:
            kwargs["base_url"] = LLM_BASE_URL
        return Anthropic(**kwargs)

    if LLM_PROVIDER == "deepseek":
        from llama_index.llms.deepseek import DeepSeek

        kwargs = {"model": LLM_MODEL, "api_key": api_key, "max_tokens": LLM_MAX_TOKENS, "timeout": FPT_TIMEOUT_SECONDS}
        if LLM_BASE_URL:
            kwargs["api_base"] = LLM_BASE_URL
        return DeepSeek(**kwargs)

    if LLM_PROVIDER == "openai_like":
        if not LLM_BASE_URL:
            raise RuntimeError(
                "LLM_PROVIDER=openai_like cần điền LLM_BASE_URL trong backend_py/.env "
                "(endpoint API tương thích OpenAI chat completions của nhà cung cấp bạn dùng)."
            )
        from llama_index.llms.openai_like import OpenAILike

        return OpenAILike(
            model=LLM_MODEL,
            api_key=api_key,
            api_base=LLM_BASE_URL,
            is_chat_model=True,
            max_tokens=LLM_MAX_TOKENS,
            timeout=FPT_TIMEOUT_SECONDS,
        )

    raise RuntimeError(
        f"LLM_PROVIDER='{LLM_PROVIDER}' không được hỗ trợ. Dùng 'anthropic', 'deepseek', hoặc 'openai_like'."
    )
