from __future__ import annotations

import json

from llama_index.core.prompts import PromptTemplate

_OUTPUT_SCHEMA_EXAMPLE = {
    "summary": "Một câu tóm tắt ngắn gọn giúp khách chọn nhanh giữa các lựa chọn.",
    "items": [
        {
            "product_id": "PHẢI trùng khớp product_id trong context bên dưới",
            "headline": "Một câu ngắn nêu điểm nổi bật nhất",
            "pros": ["Ưu điểm 1 (ngắn gọn)", "Ưu điểm 2 (ngắn gọn)"],
            "cons": ["Nhược điểm chính nếu có"],
            "recommendation_reason": "1 câu ngắn vì sao nên/không nên chọn",
        }
    ],
}

EXPLANATION_QA_TEMPLATE = PromptTemplate(
    "Bạn là trợ lý tư vấn sản phẩm điện máy. Dưới đây là dữ liệu CÁC SẢN PHẨM ĐÃ ĐƯỢC LỌC "
    "VÀ XẾP HẠNG SẴN bằng hệ thống (context) — đây là NGUỒN DUY NHẤT bạn được phép dùng:\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "QUY TẮC BẮT BUỘC (vi phạm sẽ bị chặn ở bước kiểm tra sau bởi guardrail):\n"
    "1. CHỈ được nhắc tới đúng các sản phẩm có trong context. KHÔNG được bịa thêm sản phẩm khác.\n"
    "2. CHỈ được dùng số liệu (giá, thông số) CÓ TRONG context. KHÔNG được suy diễn, làm tròn tuỳ ý, "
    "hoặc tự nghĩ ra số liệu không có trong dữ liệu.\n"
    "3. Nếu một field trong key_specs là null, hãy nói 'chưa có dữ liệu' thay vì đoán giá trị.\n"
    "4. Mỗi sản phẩm cần: 1 headline, 1-2 pros, tối đa 1 con (ưu tiên lấy gợi ý từ trường "
    "'tradeoffs' nếu có), và 1 câu recommendation_reason ngắn gọn.\n"
    "5. product_id trong output PHẢI khớp CHÍNH XÁC với product_id trong context.\n"
    "6. Output CHỈ là JSON thuần theo đúng schema mẫu bên dưới — không markdown, không giải thích thêm.\n"
    "7. Giữ output NGẮN GỌN, tổng không quá 600 token.\n\n"
    "Schema output mẫu: " + json.dumps(_OUTPUT_SCHEMA_EXAMPLE, ensure_ascii=False) + "\n\n"
    "Yêu cầu: {query_str}\n"
    "JSON:"
)
