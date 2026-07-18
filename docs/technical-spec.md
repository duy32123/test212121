# Technical Spec — AI Product Comparison Advisor

**Dự án:** Trợ lý AI so sánh và tư vấn sản phẩm theo nhu cầu thật của khách hàng
**Đối tác:** Điện Máy Xanh — Vietnam Innovation Challenge 2026
**Phạm vi ưu tiên MVP:** ngành hàng Máy lạnh và Tủ lạnh (từ `Spec_cate_gia.xlsx`), kiến trúc mở rộng được cho 12 ngành hàng còn lại (Máy giặt, Tủ đông, Máy nước nóng, Đồng hồ thông minh, Máy tính bảng...).

---

## 1. Nguyên tắc kiến trúc

Ba yêu cầu bắt buộc từ đề bài chi phối toàn bộ thiết kế:

1. **Không hỏi lại thông tin đã có** — hệ thống phải nhớ được ngữ cảnh nhiều lượt.
2. **Không bịa thông số/giá/khuyến mãi** — mọi dữ liệu sản phẩm phải đến từ catalog thật, được lọc bằng code, LLM không được tự tra cứu hay suy diễn.
3. **Giải thích được trade-off bằng ngôn ngữ dễ hiểu** — LLM chỉ đóng vai trò diễn giải trên tập dữ liệu đã được lọc và xếp hạng sẵn, không tham gia vào quyết định sản phẩm nào được đưa vào top N.

Từ đó, hệ thống backend được chia thành **4 module tách biệt, có ranh giới rõ ràng**:

```
Tin nhắn khách hàng
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│ 1. SLOT-FILLING                                          │
│   - Nhận diện category + trích xuất slot thô (LLM NLU)   │
│   - Canonical hoá field name & giá trị (code)             │
│   - Merge với conversation state cũ (code)                │
│   - Tính missing_slots (code, KHÔNG dùng LLM)             │
└─────────────────────────────────────────────────────────┘
   │
   ▼
   Đủ slot bắt buộc? ──── Chưa ──▶ Hỏi đúng slot còn thiếu
   │                                 (không hỏi lại slot đã trả lời)
   Đủ
   ▼
┌─────────────────────────────────────────────────────────┐
│ 2. RETRIEVAL / FILTER                                     │
│   - Query catalog thật (Excel → JSON/SQLite) bằng code    │
│   - Lọc theo slot đã đủ (budget, diện tích, số người...)  │
│   - Case 0 kết quả: nới ràng buộc hoặc báo rõ "chưa có"   │
└─────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│ 3. RANKING / EXPLANATION                                  │
│   - Rule-based scoring (không phải LLM) → chọn Top N      │
│   - M3 hiện chỉ ranking thuần code, chưa gọi LLM explain  │
│   - LLM sau này CHỈ nhận đúng Top N record (JSON)         │
│   - Prompt cấm LLM thêm thông tin ngoài record             │
└─────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│ 4. VALIDATION (Guardrail)                                 │
│   - Đối chiếu số liệu LLM sinh ra với record gốc          │
│   - Chặn/sửa nếu có sai lệch giá, thông số, khuyến mãi    │
│   - Gắn nguồn dữ liệu (product_id, cột dữ liệu) vào output│
└─────────────────────────────────────────────────────────┘
   │
   ▼
Frontend hiển thị kết quả + trade-off + nguồn dữ liệu
   │
   └── khách phản hồi thêm ──▶ quay lại Module 1 (update state) ──▶ Module 2
```

**Ranh giới trách nhiệm quan trọng nhất:** LLM chỉ được gọi ở 2 chỗ — (a) trích xuất slot thô từ câu nói tự nhiên, và (b) diễn giải Top N đã lọc sẵn. LLM không bao giờ là nơi quyết định "sản phẩm nào tồn tại", "giá bao nhiêu", hay "còn hàng không".

---

## 2. Kiến trúc Backend & Frontend

### 2.1 Backend

- **Ngôn ngữ/runtime:** Node.js (JavaScript), kiến trúc module hoá theo 4 module ở trên, mỗi module là một thư mục độc lập trong `backend/src/`, có thể test unit riêng lẻ.
- **Không dùng framework nặng ở giai đoạn MVP** — chỉ cần một HTTP layer mỏng (Express) bọc quanh các module logic thuần (pure functions), để dễ test và dễ thay đổi giữa các milestone.
- **State store:** giai đoạn MVP dùng in-memory store theo `session_id` (Map), thiết kế interface để có thể thay bằng Redis khi lên pilot (đúng với gợi ý "Redis session" trong các thiết kế trước đó của nhóm).
- **Data layer:** đọc `Spec_cate_gia.xlsx` một lần khi khởi động, chuẩn hoá thành JSON theo từng category, đánh index theo các trường lọc chính (budget, category, các thuộc tính lọc riêng của ngành hàng). Không dùng dữ liệu Excel trực tiếp trong runtime query.
- **LLM integration:** gọi Anthropic API (`/v1/messages`) ở 2 điểm named ở trên; luôn truyền kèm `previous_state` + `missing_slots` (module 1) hoặc `top_n_records` (module 3) trong context — không bao giờ dựa vào trí nhớ của model.

### 2.2 Frontend

- Chat UI đơn giản (web), hiển thị:
  - Hội thoại dạng bong bóng chat.
  - Câu hỏi làm rõ (nếu còn thiếu slot) dưới dạng câu hỏi tự nhiên, có thể kèm quick-reply buttons cho các slot dạng enum (ví dụ: "phòng ngủ / phòng khách / phòng bếp").
  - Kết quả Top 3 dưới dạng card so sánh: tên, giá, ảnh, 2–3 lý do nên/không nên chọn, và **nguồn dữ liệu** (mã sản phẩm) để tăng độ tin cậy.
- Không xử lý logic nghiệp vụ ở frontend — frontend chỉ render state trả về từ backend.
- **Phạm vi lượt này:** không sửa frontend, chỉ chuẩn bị API contract để frontend integrate sau.

---

## 3. User Flow

```
1. Khách: "Em muốn mua máy lạnh dưới 20 triệu cho phòng 18m²"
2. Backend (Module 1): nhận diện category=máy lạnh, budget_max=20.000.000, room_area_m2=18
   → missing: installation_location, noise_priority (ưu tiên nếu muốn hỏi thêm)
3. Backend hỏi: "Anh/chị lắp cho phòng ngủ hay phòng khách ạ?"
4. Khách: "Phòng ngủ, ít bị nắng"
5. Backend (Module 1): merge installation_location=phòng ngủ, sun_exposure=false
   → đủ slot bắt buộc (category, budget_max, room_area_m2, installation_location)
6. Backend (Module 2): lọc catalog máy lạnh theo budget ≤ 20tr, phù hợp diện tích phòng
7. Backend (Module 3): rank theo độ khớp + LLM diễn giải Top 3
8. Backend (Module 4): validate số liệu LLM sinh ra khớp với record gốc
9. Frontend hiển thị Top 3 kèm lý do & nguồn dữ liệu
10. Khách: "Bỏ cái đầu tiên đi, cho xem rẻ hơn"
    → quay lại Module 1 (update excluded_ids, budget_max giảm) → Module 2 → ...
```

---

## 4. API Contract (dự kiến, cho milestone triển khai HTTP layer)

### `POST /api/conversation/message`

Request:
```json
{
  "session_id": "sess_abc123",
  "message": "Em muốn mua máy lạnh dưới 20 triệu cho phòng 18m2"
}
```

Response (khi còn thiếu slot):
```json
{
  "session_id": "sess_abc123",
  "status": "need_clarification",
  "reply": "Anh/chị lắp máy lạnh cho phòng ngủ hay phòng khách ạ?",
  "state": {
    "category": "may_lanh",
    "slots": { "budget_max": 20000000, "room_area_m2": 18 },
    "missing_slots": ["installation_location"]
  }
}
```

Response (khi đủ slot, đã có kết quả — Module 2-3 hiện trả retrieval + ranking thuần code):
```json
{
  "session_id": "sess_abc123",
  "status": "ready",
  "state": { "category": "may_lanh", "slots": { "...": "..." }, "missing_slots": [] },
  "results": ["... Top N ranked records thuộc Milestone 3 ..."]
}
```

### `GET /api/conversation/:session_id/state`
Trả về conversation state hiện tại — hỗ trợ debug và hỗ trợ frontend khôi phục phiên.

> Lưu ý: lượt triển khai này (Milestone 1) chỉ hiện thực hoá phần logic của Module 1 (`src/state`, `src/nlu`) dưới dạng pure function có test; HTTP layer (Express route) sẽ được nối dây ở milestone kế tiếp cùng với Module 2.

---

## 5. Product Schema & Conversation State

### 5.1 Product schema (nguồn: `Spec_cate_gia.xlsx`)

Mỗi sheet Excel là một category, dùng chung nhóm cột định danh:
`model_code, sku, productidweb, category_code, brand_id, brand, giá gốc, giá khuyến mãi, khuyến mãi quà`, cộng thêm các cột thông số riêng theo ngành hàng.

**Category `may_lanh` (Máy lạnh)** — các cột dùng để lọc/tư vấn chính:
`Loại máy, Công suất đầu ra, Phạm vi sử dụng (diện tích phòng), Độ ồn, Nhãn năng lượng, Công nghệ tiết kiệm điện, Tiện ích, giá gốc, giá khuyến mãi`.

**Category `tu_lanh` (Tủ lạnh)** — các cột dùng để lọc/tư vấn chính:
`Số người sử dụng, Dung tích tổng, Số cửa, Điện năng tiêu thụ, Công nghệ tiết kiệm điện, Kiểu dáng, Cao/Ngang/Sâu, giá gốc, giá khuyến mãi`.

Các ngành hàng còn lại (Máy giặt, Tủ đông, Máy nước nóng, Đồng hồ thông minh...) dùng chung cấu trúc nạp dữ liệu (`data/loadCatalog.js`), nhưng schema slot chi tiết cho từng ngành sẽ được bổ sung ở milestone mở rộng — hiện tại rơi vào schema mặc định (`category`, `budget_max`) để không chặn luồng hội thoại.

### 5.2 Slot schema (per category) — `backend/src/schema/categorySchemas.js`

```js
may_lanh: {
  required: ["category", "budget_max", "room_area_m2", "installation_location"],
  optional: ["budget_min", "noise_priority", "power_saving_priority", "sun_exposure", "promo_preference"],
}
tu_lanh: {
  required: ["category", "budget_max", "household_size"],
  optional: ["budget_min", "installation_location", "door_type_preference", "power_saving_priority"],
}
default: {
  required: ["category", "budget_max"],
  optional: ["budget_min"],
}
```

Mỗi slot có alias map để canonical hoá field từ output NLU thô, ví dụ:
`location | vị trí lắp | nơi lắp đặt → installation_location`
`area | diện tích | dien_tich → room_area_m2`
`budget | ngân sách | ngan_sach → budget_max`

### 5.3 Conversation state schema — `backend/src/state/conversationState.js`

```ts
ConversationState {
  session_id: string
  category: string | null
  slots: Record<string, string | number | boolean>   // chỉ chứa giá trị đã canonical & hợp lệ
  missing_slots: string[]                             // luôn tính lại bằng code sau mỗi turn
  asked_slots: string[]                                // slot đã từng được hỏi (chống hỏi lặp)
  rejected_fields: Array<{ field: string, reason: string, raw_value: any }>  // field sai/không nhận diện được — GIỮ LẠI để log, không âm thầm xoá
  turn_count: number
  updated_at: ISOString
}
```

Thiết kế quan trọng: **`rejected_fields` không bao giờ bị xoá âm thầm.** Khi NLU trả về một field không hợp lệ (sai kiểu dữ liệu) hoặc không nhận diện được (không có trong alias map), hệ thống giữ lại field đó kèm lý do, để có thể log/debug và để có thể hỏi lại khách xác nhận thay vì bỏ qua trong im lặng.

---

## 6. Kế hoạch triển khai theo milestone

| Milestone | Nội dung | Trạng thái |
|---|---|---|
| **M0 — Chuẩn bị dữ liệu** | Chuẩn hoá 2 sheet Máy lạnh & Tủ lạnh từ Excel thành schema lọc được; định nghĩa category schema | Song song với M1 |
| **M1 — Slot-filling & Conversation State** | Canonical NLU, chuẩn hoá `location → installation_location`, merge state, tính missing slots bằng code, chống hỏi lặp, không âm thầm bỏ field sai, prompt builder truyền previous state + missing slots cho LLM | ✅ Đã triển khai |
| **M2 — Retrieval/Filter** (lượt này) | Nạp catalog thật từ Excel vào bộ nhớ, parse các trường thông số dạng chuỗi tiếng Việt không đồng nhất, filter theo slot đã đủ bằng code, xử lý case 0 kết quả bằng cách nới ràng buộc theo trình tự định trước hoặc báo rõ "chưa có dữ liệu" | ✅ Triển khai trong lượt này |
| **M3 — Rule-based Ranking** | Module `src/ranking/rankProducts.js` nhận kết quả `retrieveForState`, chọn Top N mặc định Top 3, tính score deterministic 0–100, trả `score_breakdown`, `matched_reasons`, `tradeoffs`, `missing_data`, `source`; tie-break theo giá rồi product_id; xử lý `not_ready`/`no_results`; orchestrator `src/recommendForState.js` nối state → retrieval/filter → ranking. Chưa làm LLM explanation. | ✅ Triển khai trong lượt này |
| **M4 — Validation/Guardrail** (lượt này) | Gọi LLM giải thích Top N qua `src/llm/llmClient.js` (API key ngoài, cấu hình qua `.env`), sau đó `src/validation/validateExplanation.js` đối chiếu từng claim số (giá, m², dB, lít, người) với record gốc; loại sản phẩm ngoài Top N, thay claim sai lệch bằng cảnh báo an toàn, giữ nguyên sản phẩm hợp lệ dù LLM bỏ sót; orchestrator toàn pipeline `src/adviseForState.js` | ✅ Triển khai trong lượt này |
| **M5 — HTTP layer + Frontend integration** | Nối Express route theo API contract ở mục 4, kết nối frontend chat UI | Kế tiếp |
| **M6 — Demo & pilot plan** | Chuẩn bị video demo, lộ trình pilot 1-2 trang theo yêu cầu D3 | Cuối cùng |

---

## 7. Việc đã triển khai trong lượt này (Milestone 1)

- `backend/src/schema/categorySchemas.js` — schema slot cho `may_lanh`, `tu_lanh`, `default` + alias map.
- `backend/src/nlu/canonicalize.js` — canonical hoá field/giá trị từ NLU thô; parse số từ chuỗi tiếng Việt (`"20 triệu"`, `"18m2"`); tách riêng `rejected_fields` thay vì xoá âm thầm.
- `backend/src/state/conversationState.js` — factory tạo state rỗng theo schema.
- `backend/src/state/merge.js` — merge slot mới vào state cũ, cộng dồn `rejected_fields`, không cho phép slot hợp lệ bị ghi đè bởi giá trị rác.
- `backend/src/state/missingSlots.js` — tính `missing_slots` bằng code, dựa 100% vào schema + state, không qua LLM.
- `backend/src/state/clarification.js` — chọn slot tiếp theo để hỏi, ưu tiên slot chưa từng hỏi, chống lặp câu hỏi khi state không đổi.
- `backend/src/nlu/promptBuilder.js` — build prompt cho LLM NLU, luôn nhúng `previous_state` + `missing_slots`, cấm hỏi lại slot đã có giá trị.
- `backend/tests/*.test.js` — test cho toàn bộ các module trên, gồm test chống lặp câu hỏi làm rõ qua nhiều lượt hội thoại giả lập.

## 8. Việc đã triển khai ở Milestone 2 (Retrieval/Filter)

- `backend/data/Spec_cate_gia.xlsx` — copy nguồn dữ liệu gốc vào repo để `loadCatalog` chạy được độc lập (không phụ thuộc đường dẫn upload tạm thời).
- `backend/src/data/parseSpecs.js` — các hàm parse thông số dạng chuỗi tiếng Việt không đồng nhất từ Excel (`"Từ 30 - 40m² (từ 80 đến 120m³)"`, `"Dàn lạnh: 45/34/29 dB - Dàn nóng: 51 dB"`, `"Trên 5 người"`, `"Đang cập nhật"`...) thành giá trị có cấu trúc (`{min, max}` hoặc số); parse không được → trả `null`, không suy diễn giá trị mặc định.
- `backend/src/data/loadCatalog.js` — đọc 2 sheet ưu tiên (Máy lạnh, Tủ Lạnh) từ `Spec_cate_gia.xlsx`, chuẩn hoá thành product object có `effective_price` (ưu tiên giá khuyến mãi, fallback giá gốc, `null` nếu cả hai đều thiếu — không bịa giá), giữ nguyên `_raw` row gốc để phục vụ trích dẫn nguồn dữ liệu ở Module 4.
- `backend/src/data/catalogStore.js` — cache catalog đã load, tránh đọc lại Excel mỗi lần gọi.
- `backend/src/retrieval/filterProducts.js` — module lọc bằng code (không dùng LLM), theo trình tự nới ràng buộc khi 0 kết quả:
  - Máy lạnh: `strict` (đúng ngân sách + diện tích) → `dropped_room_area_constraint` (bỏ ràng buộc diện tích) → `increased_budget_15pct` (nới ngân sách +15%) → `no_results` (báo rõ, không bịa sản phẩm).
  - Tủ lạnh: tương tự với `dropped_household_constraint` thay cho diện tích.
  - Sản phẩm không có `effective_price` (thiếu cả giá gốc lẫn giá khuyến mãi) luôn bị loại, không được đưa vào tư vấn.
- `backend/src/retrieveForState.js` — nối Module 1 (conversation state) với Module 2: chỉ gọi filter khi `missing_slots` rỗng, trả `not_ready` nếu state chưa đủ slot.
- `backend/tests/parseSpecs.test.js`, `loadCatalog.test.js`, `filterProducts.test.js`, `retrieveForState.test.js` — test unit cho từng hàm parse/filter, và test tích hợp end-to-end từ hội thoại slot-filling tới kết quả lọc trên catalog thật.


## 9. Milestone 3 — Rule-based Ranking Contract

`backend/src/ranking/rankProducts.js` là module ranking thuần code, không gọi LLM. Input là kết quả từ `retrieveForState` và conversation state/slots; output là Top N (mặc định Top 3) với các field:

- `rank`, `product_id`, `model_code`, `effective_price`, `total_score`.
- `score_breakdown`: điểm thành phần 0–100. Máy lạnh chấm ngân sách, diện tích, độ ồn, tiết kiệm điện, nắng nếu khách có nêu. Tủ lạnh chấm ngân sách, số người, dung tích, loại cửa, tiết kiệm điện nếu khách có nêu.
- `matched_reasons`, `tradeoffs`, `missing_data`. Field null/không parse được không được suy diễn; ranking ghi vào `missing_data` và dùng điểm trung lập 50.
- `relaxed_constraints`: copy từ retrieval khi status là `relaxed` để biết constraint nào đã được nới.
- `source`: clone của product record gốc để Milestone 4–5 validate/render mà không cần LLM tự tra cứu.

Tie-break ổn định: `total_score` giảm dần, sau đó `effective_price` tăng dần, cuối cùng `product_id` tăng dần. `backend/src/recommendForState.js` là orchestrator nối conversation state → retrieval/filter → ranking.

## 10. Milestone 4 — Validation/Guardrail Contract

Module cuối cùng trong 4 module bắt buộc. Đây là nơi LLM thật sự được gọi
lần đầu trong pipeline (Module 1 chỉ dùng LLM để trích slot, đã tách riêng
ở prompt của M1) để **diễn giải** Top N đã lọc/rank — sau đó guardrail đối
chiếu lại toàn bộ số liệu trước khi trả cho khách.

### 10.1 Luồng xử lý

```
Top N (từ M3: rankProducts)
   │
   ▼
buildExplanationPrompt(rankingResult, state)
   -> prompt CHỈ chứa đúng field cần thiết của Top N (không lộ toàn bộ _raw)
   -> system prompt cấm bịa sản phẩm, cấm suy diễn số liệu, ép output JSON thuần
   │
   ▼
llmClient({system, user})  — gọi Anthropic Messages API (hoặc provider tương
   thích), model/API key do người dùng tự cấu hình qua backend/.env
   │
   ▼
parseJsonFromLlmText()  — bóc markdown fence nếu có, JSON.parse
   │  parse lỗi → status "llm_parse_error", không crash pipeline
   ▼
validateExplanation(llmOutput, rankingResult, state)   ◀── GUARDRAIL
   1. product_id ngoài Top N            → loại bỏ item (rejected_items)
   2. effective_price hiển thị          → LUÔN lấy từ record gốc, bỏ qua số LLM viết
   3. Mỗi field text (headline/pros/cons/recommendation_reason):
        trích claim số (tiền, m², dB, lít, người) → so khớp với tập
        "known facts" dựng từ chính Top N + slot khách hàng (dung sai
        3% cho tiền, 2% cho thông số) → claim sai lệch bị thay bằng
        thông báo an toàn (FALLBACK_TEXT), ghi log vào `corrections`
   4. Sản phẩm có trong Top N nhưng LLM bỏ sót không nhắc tới → vẫn được
      trả về (kèm cờ `llm_explanation_missing`) thay vì mất trắng khỏi kết quả
   5. Nếu mọi item đều bị loại/thiếu giải thích → status "blocked"
   │
   ▼
Kết quả cuối cho frontend: { status, summary, items[], corrections[],
   rejected_items[], ranking, retrieval, state }
```

### 10.2 Tập "known facts" — cơ chế đối chiếu chống hallucination

`src/validation/knownFacts.js` dựng một tập số liệu "đã xác minh" duy nhất
từ chính dữ liệu đã lọc/rank (không phải từ LLM):

- **Tiền (money):** `effective_price` của từng sản phẩm trong Top N,
  `budget_max`/`budget_min` khách đã cho, và **hiệu số giữa các mức giá**
  trong Top N (để câu so sánh hợp lệ như "rẻ hơn 3 triệu" không bị chặn
  nhầm là hallucination).
- **Thông số (spec):** theo từng đơn vị `m²`, `dB`, `lít`, `người` — lấy từ
  `room_area_range`, `noise_db`, `capacity_total_liters`, `household_range`
  của từng sản phẩm, cộng thêm giá trị slot khách hàng đã cho
  (`room_area_m2`, `household_size`).

Bất kỳ số nào LLM nhắc tới (được trích bằng `src/validation/extractClaims.js`)
mà không khớp trong dung sai với tập trên đều bị coi là **chưa xác minh
được** — dù số đó "nghe hợp lý" — và bị thay thế, không được suy diễn thêm
là đúng hay sai.

### 10.3 Cấu hình LLM (API key ngoài)

`src/llm/llmClient.js` không hardcode bất kỳ key nào. Người dùng tự cấu
hình qua `backend/.env` (copy từ `backend/.env.example`):

```
LLM_API_KEY=...        # bắt buộc — API key thật của bạn
LLM_MODEL=claude-sonnet-4-6
LLM_BASE_URL=https://api.anthropic.com/v1/messages
```

`src/config/env.js` tự nạp `.env` (không cần thêm dependency `dotenv`),
không ghi đè biến môi trường đã set sẵn từ shell/CI. Toàn bộ hàm nhận
LLM qua tham số `options.llmClient` (dependency injection) — production
dùng client thật, test luôn dùng client giả lập để không phụ thuộc mạng
hay API key khi chạy `npm test`.

### 10.4 Orchestrator toàn pipeline

`src/adviseForState.js` nối trọn 4 module (trừ bước hỏi làm rõ của M1, vốn
xảy ra ở các turn trước đó qua `src/turn.js`):

```
adviseForState(state, options)
  = retrieveForState(state)        // M2
  → rankProducts(retrieval, state) // M3
  → generateExplanation(ranking, state, options.llmClient) // M4 (gọi LLM + guardrail)
```

Nếu `retrieval`/`ranking` chưa sẵn sàng hoặc không có kết quả, `adviseForState`
trả về ngay, **không gọi LLM** — tránh tốn API call vô ích và tránh LLM tự
"chữa cháy" khi chưa có dữ liệu.

---

## 11. Viết lại bằng Python — tích hợp llama_index & guardrails-ai thật (Milestone 5)

Từ milestone này, backend được **viết lại hoàn toàn bằng Python** (`backend_py/`), song song giữ nguyên
4 module kiến trúc (Slot-filling → Retrieval/Filter → Ranking → Explanation + Validation/Guardrail), và
bổ sung 2 thư viện được yêu cầu áp dụng thật (cài qua `pip`, không copy source repo):

- **llama_index** (`llama-index-core` + `llama-index-llms-anthropic`) — dùng ở Module 3 (Explanation):
  mỗi sản phẩm trong Top N (đã lọc + rank bằng code ở Module 2/3) được chuyển thành 1 `TextNode`, đưa vào
  `get_response_synthesizer()` cùng prompt ép JSON nghiêm ngặt. Đây là RAG trên **context đã lọc sẵn bằng
  code** — KHÔNG phải semantic search trên toàn bộ catalog (dữ liệu catalog có cấu trúc, lọc chính xác
  bằng so sánh số vẫn đúng hơn similarity search). llama_index cho phép truy vết `source_nodes` — biết
  chính xác node nào (sản phẩm nào) đã được đưa vào ngữ cảnh sinh câu trả lời.
- **guardrails-ai** — dùng ở Module 4 (Validation/Guardrail): output LLM được validate theo
  `ExplanationOutput` (Pydantic model) qua `Guard.for_pydantic()`, gắn thêm validator tuỳ chỉnh
  `ClaimsVerified` (local, không cần Guardrails Hub/network) — đối chiếu từng claim số (giá, m², dB, lít,
  người) với tập "known facts" dựng từ chính Top N + slot khách hàng, tự động sửa (`on_fail="fix"`) bằng
  cách thay claim sai lệch bằng thông báo an toàn, đồng thời loại bỏ sản phẩm có `product_id` ngoài Top N.

### 11.1 Tổng quát hoá cho 14 category (dùng `schemas/registry.json`)

Toàn bộ Module 2 (`catalog/load_catalog.py`) đọc `Spec_cate_gia.xlsx` theo đúng mapping cột trong
`schemas/registry.json` (do BTC cung cấp) — **không hardcode category hay tên cột nào trong code**. Thêm
1 category mới = thêm entry vào `registry.json` + schema JSON tương ứng.

Slot hội thoại (Module 1) và tiêu chí lọc/rank (Module 2/3) được tổng quát hoá qua
`conversation/slot_schemas.py` — mỗi category khai báo `RangeSlotConfig` (slot nào ứng với field số nào
trong `spec`, parse theo kiểu gì). Điều này khắc phục lỗi thiết kế ở bản Node cũ (category lạ bị rơi
nhầm vào nhánh ranking của máy lạnh) — Module 3 giờ dùng đúng 1 hàm chấm điểm chung cho mọi category,
đọc cấu hình thay vì switch theo tên category.

### 11.2 Cấu trúc thư mục

```
backend_py/
  .env.example
  requirements.txt
  data/Spec_cate_gia.xlsx
  schemas/                 # registry.json + *.schema.json (BTC cung cấp)
  app/
    config/settings.py     # đọc .env, tắt telemetry guardrails/otel
    catalog/                # registry.py, parse_specs.py, load_catalog.py, catalog_store.py (M2 nạp dữ liệu)
    conversation/            # slot_schemas, state, canonicalize, merge, missing_slots, clarification, turn (M1)
    retrieval/                # filter_products.py, retrieve_for_state.py (M2)
    ranking/                   # rank_products.py (M3, rule-based)
    explanation/                 # nodes.py, prompt.py, synthesizer.py, llm_factory.py (M3 gọi LLM qua llama_index)
    guardrail/                    # claim_extraction, known_facts, output_schema, validators, guard (M4, guardrails-ai)
    pipeline.py                    # advise_for_state() — orchestrator M2→M3→M4
    server.py                       # FastAPI, giữ nguyên API contract cũ cho frontend
  tests/                     # pytest, 92 test — mọi test LLM dùng CustomLLM giả lập, không gọi mạng
frontend/                   # giữ nguyên, không sửa (đã tương thích API contract)
```

### 11.3 Cách chạy

```bash
cd backend_py
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # điền LLM_API_KEY thật để chạy với LLM thật
pytest -q              # 92 passed — không cần API key, mọi LLM call đều giả lập
uvicorn app.server:app --reload --port 3000
```

---

## 12. Chuyển catalog source sang DMX JSON (Milestone 6)

Catalog source đổi từ `Spec_cate_gia.xlsx` (14 category, dữ liệu demo) sang
**`backend_py/data/products_detail.json`** (dữ liệu DMX thật, 119 category,
13.754 sản phẩm), mapping qua `schemas/dmx_registry.json` (BTC cung cấp).

### 12.1 Nguồn dữ liệu & chuẩn bị

`products_detail.json` được sinh 1 lần (offline, ngoài production) từ
`products_detail.xlsx` (2 sheet: `products` dạng bảng rộng, `specs` dạng
long-format `product_id/spec_key/spec_value`) bằng:

```bash
python scripts/build_products_detail_json.py \
  --input products_detail.xlsx \
  --output backend_py/data/products_detail.json
```

Script này **giữ nguyên tên field thô tiếng Việt** (không map/parse gì) —
việc map sang field canonical thuộc về production loader, không phải script.

### 12.2 Production loader — KHÔNG dùng Excel

- `app/catalog/dmx_registry.py` — nạp `schemas/dmx_registry.json`, expose
  `top_level_mapping` (field cấp 1: giá, tên, brand...) và `spec_map` theo
  category (hiện chỉ "Máy lạnh" có spec_map chi tiết — các category khác
  BTC sẽ bổ sung dần). Parser dispatch (`parse_area`, `parse_noise`,
  `parse_btu`, `parse_inverter`, `parse_year`, `parse_kwh`, `clean_str`...)
  hoàn toàn theo TÊN khai báo trong JSON — không hardcode category nào.
- `app/catalog/load_dmx_catalog.py` — đọc DUY NHẤT `products_detail.json`,
  **không import pandas theo đường Excel nào**. Raise `DmxCatalogError` rõ
  ràng nếu file thiếu/rỗng/sai cấu trúc/thiếu field `product_id` — không
  tự tạo dữ liệu giả.
- `app/catalog/catalog_store.py` — production chỉ gọi
  `load_catalog_from_json()`, không còn import `load_catalog_from_excel`.

`app/catalog/load_catalog.py` + `app/catalog/registry.py` (Excel, dùng
`registry.json` cũ) được **giữ lại nguyên trạng làm module legacy** (test
hồi quy riêng), nhưng **không còn được `catalog_store` hay bất kỳ đường
production nào import**.

### 12.3 Quyết định định danh sản phẩm

`products_detail.json` không có field `productidweb`/`sku` tách biệt như dữ
liệu Excel cũ — chỉ có `product_id` (số, duy nhất, chính là ID trang web
dienmayxanh.com) và `productcode` (dạng mã vạch, không phải model code đọc
được). Quyết định:

- `product_id` (canonical) = `str(product_id)` thô — đã là định danh duy
  nhất, đúng tinh thần "productidweb".
- `sku` = `str(productcode)` nếu có.
- `model_code` = `None` — **không gán `productcode` vào `model_code`** vì
  đó là mã vạch, gán vào sẽ tạo cảm giác sai là "model đọc được", vi phạm
  nguyên tắc không bịa/gán sai ngữ nghĩa dữ liệu.

### 12.4 Tác động tới slot schema (Module 1) & category alias

- Category nào **chưa có `spec_map`** trong `dmx_registry.json` (mọi
  category trừ `air_conditioner` tại thời điểm này) được hạ về schema mặc
  định (chỉ hỏi `budget_max`) — tránh tình trạng range slot (vd
  `household_size` cho tủ lạnh) luôn strict-match thất bại một cách âm
  thầm vì field nguồn không tồn tại trong spec DMX.
- Category alias (`conversation/canonicalize.py`) đổi từ danh sách thủ công
  sang: alias tự nhiên cho `air_conditioner` + `slugify_category_name()`
  (NFKD, tự động) cho 118 category còn lại, **xác thực lại với catalog thật
  đã nạp** trước khi chấp nhận — tránh chấp nhận nhầm 1 chuỗi bất kỳ trông
  giống category nhưng không khớp sản phẩm nào.

### 12.5 Frontend thay thế

Frontend (`frontend/`) được thay bằng bản UI mới (sidebar lịch sử chat,
dark mode, thẻ sản phẩm dạng lưới) — giữ nguyên toàn bộ UI/UX, chỉ thay
"bộ não" (trước đây là `MOCK_CATALOG` + NLP heuristic chạy hoàn toàn trong
trình duyệt) bằng lời gọi API thật tới `POST /api/conversation/message`.
Mọi số liệu hiển thị (giá, thông số, lý do chọn, trade-off) lấy trực tiếp
từ response backend — frontend không tự tính toán hay bịa số liệu sản phẩm.
