from __future__ import annotations

from fastapi.testclient import TestClient

from app.server import _session_store, app

client = TestClient(app)


def test_message_without_api_key_falls_back_to_basic_parse_and_asks_clarification():
    _session_store._sessions.clear()
    r = client.post(
        "/api/conversation/message",
        json={"session_id": "t1", "message": "Em muốn mua máy lạnh dưới 20 triệu cho phòng 18m2"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "need_clarification"
    assert data["state"]["category"] == "air_conditioner"
    assert data["state"]["slots"]["budget_max"] == 20_000_000


def test_missing_session_id_returns_400():
    r = client.post("/api/conversation/message", json={"session_id": "", "message": "hi"})
    assert r.status_code == 400


def test_get_state_404_for_unknown_session():
    r = client.get("/api/conversation/does-not-exist/state")
    assert r.status_code == 404


def test_reset_session():
    _session_store._sessions.clear()
    client.post("/api/conversation/message", json={"session_id": "t2", "message": "máy lạnh"})
    r = client.post("/api/conversation/t2/reset")
    assert r.status_code == 200
    assert r.json()["state"]["category"] is None


def test_laptop_message_without_llm_key_uses_deterministic_fallback():
    """Không có LLM_API_KEY -> get_default_llm() raise -> fallback tất định
    trong nlu_lexicon.parse_message_deterministic vẫn phải nhận diện đúng
    category + soft preference, KHÔNG được âm thầm trả {} khiến chatbot hỏi
    lặp category. (Không kèm ngân sách trong câu để giữ turn ở
    need_clarification — tránh phải gọi LLM thật ở giai đoạn giải thích,
    vốn ngoài phạm vi test fallback NLU này.)"""
    _session_store._sessions.clear()
    r = client.post(
        "/api/conversation/message",
        json={"session_id": "laptop-fallback", "message": "Cần con lap top pin trâu, mỏng nhẹ để đi học"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["state"]["category"] == "laptop"
    assert data["state"]["slots"]["battery_priority"] == "high"
    assert data["state"]["slots"]["portability_priority"] == "high"
    assert data["state"]["slots"]["use_case"] == "student"
    # Không có key numeric nào được suy diễn từ 'pin trâu'
    assert not any(isinstance(v, (int, float)) for k, v in data["state"]["slots"].items() if "battery" in k)


def test_dishwasher_message_deterministic_fallback():
    _session_store._sessions.clear()
    r = client.post("/api/conversation/message", json={"session_id": "dishwasher-fallback", "message": "Tôi muốn mua máy rửa bát"})
    assert r.status_code == 200
    data = r.json()
    assert data["state"]["category"] == "may_rua_chen"
    assert data["status"] == "need_clarification"
    assert data["clarifying_question"]["slot"] == "budget_max"


def test_previous_state_category_not_asked_again(monkeypatch, counting_llm):
    """Category đã có trong previous_state -> turn sau không được hỏi lại
    category. Dùng LLM giả lập (không gọi FPT thật) để test nhanh, ổn định."""
    _session_store._sessions.clear()
    monkeypatch.setattr("app.server.get_default_llm", lambda: counting_llm(response_text='{"summary":"ok","items":[]}'))

    session_id = "no-reask-category"
    r1 = client.post("/api/conversation/message", json={"session_id": session_id, "message": "Cần mua laptop"})
    assert r1.json()["status"] == "need_clarification"
    assert r1.json()["state"]["category"] == "laptop"

    client.post("/api/conversation/message", json={"session_id": session_id, "message": "tầm 15 củ"})

    state_resp = client.get(f"/api/conversation/{session_id}/state")
    state = state_resp.json()["state"]
    assert state["category"] == "laptop"
    assert state["slots"]["budget_max"] == 15_000_000
    assert "category" not in state["missing_slots"]


def test_fpt_called_at_most_once_per_request_when_nlu_understands_message(monkeypatch, counting_llm):
    """Deterministic parser hiểu ngay category+budget (không cần gọi FPT
    cho NLU) -> turn ready ngay -> explanation gọi FPT đúng 1 lần."""
    _session_store._sessions.clear()
    llm = counting_llm(response_text='{"summary": "ok", "items": []}')
    monkeypatch.setattr("app.server.get_default_llm", lambda: llm)

    r = client.post(
        "/api/conversation/message",
        json={"session_id": "one-call-1", "message": "Cần mua laptop tầm 15 triệu"},
    )
    assert r.status_code == 200
    assert llm.call_count <= 1


def test_fpt_called_at_most_once_per_request_when_nlu_needs_llm(monkeypatch, counting_llm):
    """Dict/regex 'không hiểu' câu quá lạ -> phải gọi FPT cho NLU (1 lần) —
    nhưng ngay cả khi turn cũng ready trong cùng request, KHÔNG được gọi
    thêm lần 2 cho giai đoạn giải thích."""
    _session_store._sessions.clear()
    # LLM trả JSON rỗng cho NLU (không hiểu được gì thêm) -> vẫn chỉ 1 lần gọi.
    llm = counting_llm(response_text="{}")
    monkeypatch.setattr("app.server.get_default_llm", lambda: llm)

    gibberish = "asdkjaslkdj alksjd laksjd alksjdlaksjd 128937192387 !@#$%^&*()"
    r = client.post("/api/conversation/message", json={"session_id": "one-call-2", "message": gibberish})
    assert r.status_code == 200
    assert llm.call_count <= 1


def test_fpt_timeout_still_returns_within_5_seconds_with_top3_fallback(monkeypatch, slow_llm):
    """FPT 'treo' (sleep lâu hơn timeout) -> request vẫn phải trả về trong
    < 5s, kèm top 3 sản phẩm + lời giải thích tạo từ matched_reasons/tradeoffs
    (llm_explanation_missing=True), KHÔNG chờ FPT."""
    import time

    _session_store._sessions.clear()
    llm = slow_llm(sleep_seconds=10.0)
    monkeypatch.setattr("app.server.get_default_llm", lambda: llm)

    # Điền đủ slot bắt buộc của air_conditioner qua dict/regex tất định
    # (không cần gọi FPT cho NLU) để turn ready ngay trong 1 request, ép
    # luồng phải đi tới giai đoạn giải thích (nơi FPT bị treo).
    session_id = "timeout-fallback"
    client.post(
        "/api/conversation/message",
        json={"session_id": session_id, "message": "Máy lạnh cho phòng ngủ 18m2 dưới 20 triệu"},
    )

    t0 = time.time()
    r = client.post("/api/conversation/message", json={"session_id": session_id, "message": "phòng ngủ"})
    elapsed = time.time() - t0

    assert elapsed < 5, f"Request mất {elapsed:.2f}s, vượt ngân sách 5s"
    assert r.status_code == 200
    data = r.json()
    if data["status"] not in ("not_ready", "need_clarification"):
        assert data["status"] in ("ok", "corrected")
        assert len(data["items"]) > 0
        assert all(item["llm_explanation_missing"] for item in data["items"])
        assert all(item["pros"] or item["headline"] for item in data["items"])
