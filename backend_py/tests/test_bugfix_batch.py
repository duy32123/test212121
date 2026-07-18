from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.catalog.catalog_store import get_catalog
from app.conversation.canonicalize import canonicalize
from app.conversation.merge import merge_slots
from app.conversation.missing_slots import compute_missing_slots
from app.conversation.nlu_lexicon import extract_brand_from_text, parse_message_deterministic
from app.conversation.state import create_conversation_state
from app.pipeline import build_local_explanation
from app.ranking.rank_products import RankingResult
from app.server import _session_store, app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Bug 1 — name/brand/image/url phải có mặt xuyên suốt, kể cả card fallback
# (chưa qua AI).
# ---------------------------------------------------------------------------


def _ranked_item(**overrides):
    base = {
        "product_id": "12345",
        "model_code": None,
        "name": "Máy lạnh Panasonic Inverter 1 HP",
        "brand": "Panasonic",
        "image": "https://cdn.dienmayxanh.com/panasonic-ac.jpg",
        "url": "https://www.dienmayxanh.com/may-lanh/panasonic-inverter-1-hp",
        "effective_price": 9_000_000,
        "matched_reasons": ["Phù hợp ngân sách."],
        "tradeoffs": [],
        "missing_data": [],
    }
    base.update(overrides)
    return base


def test_local_fallback_explanation_carries_name_brand_image_url():
    ranking = RankingResult(status="ok", results=[_ranked_item()])
    state = SimpleNamespace(slots={"budget_max": 10_000_000})

    explanation = build_local_explanation(ranking, state)

    assert len(explanation.items) == 1
    item = explanation.items[0]
    assert item["name"] == "Máy lạnh Panasonic Inverter 1 HP"
    assert item["brand"] == "Panasonic"
    assert item["image"] == "https://cdn.dienmayxanh.com/panasonic-ac.jpg"
    assert item["url"] == "https://www.dienmayxanh.com/may-lanh/panasonic-inverter-1-hp"
    assert item["llm_explanation_missing"] is True


def test_catalog_products_have_name_and_url_loaded_from_products_detail_json():
    """Xác nhận load_dmx_catalog.py không còn bỏ mất name/image/url (bug gốc)."""
    catalog = get_catalog()
    ac = catalog["air_conditioner"]
    with_name = [p for p in ac if p.get("name")]
    with_url = [p for p in ac if p.get("url")]
    assert len(with_name) / len(ac) > 0.9
    assert len(with_url) / len(ac) > 0.9
    # URL phải là URL Điện Máy Xanh thật
    assert all("dienmayxanh.com" in p["url"] for p in with_url[:20])


def test_fpt_timeout_fallback_card_still_has_name_and_real_url(monkeypatch, slow_llm):
    """Kết hợp với test timeout ở lượt trước: khi FPT treo, card fallback
    vẫn phải có tên sản phẩm thật và URL Điện Máy Xanh thật (không chỉ có
    matched_reasons/giá)."""
    _session_store._sessions.clear()
    llm = slow_llm(sleep_seconds=10.0)
    monkeypatch.setattr("app.server.get_default_llm", lambda: llm)

    session_id = "timeout-name-url"
    client.post(
        "/api/conversation/message",
        json={"session_id": session_id, "message": "Máy lạnh cho phòng ngủ 18m2 dưới 20 triệu"},
    )
    r = client.post("/api/conversation/message", json={"session_id": session_id, "message": "phòng ngủ"})
    data = r.json()

    if data["status"] in ("ok", "corrected"):
        assert len(data["items"]) > 0
        for item in data["items"]:
            assert item["name"], "Card fallback thiếu tên sản phẩm"
            assert item["url"], "Card fallback thiếu URL"
            assert "dienmayxanh.com" in item["url"]


# ---------------------------------------------------------------------------
# Bug 2 — câu trả lời NGẮN theo đúng slot đang hỏi không bị hỏi lặp, không
# cần gọi FPT.
# ---------------------------------------------------------------------------


def test_bare_number_answers_short_answer_parser_directly():
    assert parse_message_deterministic("4", expected_slot="household_size") == {"household_size": 4.0}
    assert parse_message_deterministic("18", expected_slot="room_area_m2") == {"room_area_m2": 18.0}
    assert parse_message_deterministic("300", expected_slot="capacity_liters") == {"capacity_liters": 300.0}
    assert parse_message_deterministic("có", expected_slot="power_saving_priority") == {"power_saving_priority": True}
    assert parse_message_deterministic("không", expected_slot="power_saving_priority") == {"power_saving_priority": False}


def test_household_size_short_answer_not_reasked_and_no_fpt_call(monkeypatch, counting_llm):
    """'4' sau câu hỏi số người -> household_size được ghi nhận, KHÔNG hỏi
    lặp, và KHÔNG gọi FPT (dict/regex đã hiểu được)."""
    _session_store._sessions.clear()
    llm = counting_llm(response_text="{}")
    monkeypatch.setattr("app.server.get_default_llm", lambda: llm)

    session_id = "household-short-answer"
    r1 = client.post("/api/conversation/message", json={"session_id": session_id, "message": "Tôi muốn mua tủ lạnh"})
    assert r1.json()["status"] == "need_clarification"
    assert r1.json()["clarifying_question"]["slot"] in ("budget_max", "household_size")

    # Trả lời câu hỏi số người bằng số trần "4"
    asked_slot = r1.json()["clarifying_question"]["slot"]
    if asked_slot != "household_size":
        # hỏi budget trước -> trả lời budget rồi mới tới household_size
        client.post("/api/conversation/message", json={"session_id": session_id, "message": "15 triệu"})

    r2 = client.post("/api/conversation/message", json={"session_id": session_id, "message": "4"})
    data2 = r2.json()

    state_resp = client.get(f"/api/conversation/{session_id}/state")
    state = state_resp.json()["state"]
    assert state["slots"].get("household_size") == 4.0
    assert "household_size" not in state["missing_slots"]
    # Không hỏi lặp lại household_size ở turn kế tiếp
    if data2["status"] == "need_clarification":
        assert data2["clarifying_question"]["slot"] != "household_size"
    # Dict/regex đã hiểu "4" mà không cần FPT cho bước NLU — tổng số lần
    # gọi FPT của cả request tối đa 1 (chỉ có thể xảy ra ở giai đoạn giải
    # thích SAU KHI đã đủ slot, không phải để hiểu câu trả lời "4").
    assert llm.call_count <= 1


def test_yes_no_short_answer_for_priority_slot_not_reasked():
    state = create_conversation_state("prio-test")
    state = merge_slots(state, canonicalize({"category": "air_conditioner", "budget_max": "20 triệu", "room_area_m2": "18"}, state.category))
    missing_before = compute_missing_slots(state)
    assert "installation_location" in missing_before

    state = merge_slots(state, canonicalize({"installation_location": "phòng ngủ"}, state.category))
    # Sau khi đủ slot bắt buộc, thử trả lời "có" cho power_saving_priority (optional)
    from app.conversation.nlu_lexicon import parse_short_answer_for_slot

    short = parse_short_answer_for_slot("có", "power_saving_priority")
    state = merge_slots(state, canonicalize(short, state.category))
    assert state.slots["power_saving_priority"] is True
    assert compute_missing_slots(state) == []


# ---------------------------------------------------------------------------
# Bug 3 — alias "đh"/"dh" + brand "pana", tiếp tục nhận diện category dù
# raw_extraction đã có field khác.
# ---------------------------------------------------------------------------


def test_dh_alias_resolves_to_air_conditioner():
    known = set(get_catalog().keys())
    for phrase in ("đh", "dh", "mua đh gấp", "cần con dh"):
        result = parse_message_deterministic(phrase, known_categories=known)
        assert result.get("category") == "air_conditioner", phrase


def test_pana_alias_resolves_to_panasonic_brand():
    assert extract_brand_from_text("pana") == "Panasonic"
    assert extract_brand_from_text("mua con pana dùm em") == "Panasonic"
    assert extract_brand_from_text("Panasonic") == "Panasonic"


def test_full_scenario_dh_pana_budget_location_asks_area_next(monkeypatch, counting_llm):
    """'Mua đh pana dưới 15 củ cho phòng ngủ' -> nhận đúng category=air_conditioner,
    brand=Panasonic, budget_max=15tr, installation_location=phòng ngủ, TẤT CẢ
    qua dict/regex (không gọi FPT), và hỏi tiếp room_area_m2 (slot còn thiếu
    duy nhất của air_conditioner)."""
    _session_store._sessions.clear()
    llm = counting_llm(response_text="{}")
    monkeypatch.setattr("app.server.get_default_llm", lambda: llm)

    r = client.post(
        "/api/conversation/message",
        json={"session_id": "dh-pana-scenario", "message": "Mua đh pana dưới 15 củ cho phòng ngủ"},
    )
    data = r.json()

    assert data["state"]["category"] == "air_conditioner"
    assert data["state"]["slots"].get("brand") == "Panasonic"
    assert data["state"]["slots"].get("budget_max") == 15_000_000
    assert data["state"]["slots"].get("installation_location") == "phòng ngủ"

    assert data["status"] == "need_clarification"
    assert data["clarifying_question"]["slot"] == "room_area_m2"

    # Toàn bộ nhận diện qua dict/regex — không cần gọi FPT
    assert llm.call_count == 0


def test_deterministic_parser_keeps_trying_category_even_with_partial_fields(monkeypatch, counting_llm):
    """Nếu dict/regex lấy được ngân sách nhưng KHÔNG nhận diện được category
    (và state chưa có category), hệ thống phải escalate sang FPT để tiếp
    tục nhận diện category — không dừng lại chỉ vì raw_extraction khác rỗng."""
    _session_store._sessions.clear()
    llm = counting_llm(response_text='{"category": "air_conditioner"}')
    monkeypatch.setattr("app.server.get_default_llm", lambda: llm)

    # "con máy làm lạnh phòng" không khớp alias category nào đã curate,
    # nhưng "15 triệu" vẫn được dict/regex nhận diện là ngân sách.
    r = client.post(
        "/api/conversation/message",
        json={"session_id": "partial-needs-llm", "message": "con máy làm lạnh phòng tầm 15 triệu"},
    )
    data = r.json()

    assert llm.call_count == 1  # có escalate gọi FPT để tìm category
    assert data["state"]["category"] == "air_conditioner"
    assert data["state"]["slots"].get("budget_max") == 15_000_000
