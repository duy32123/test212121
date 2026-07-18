"""
conversation/slot_schemas.py — 2 loại cấu hình tách biệt nhưng liên quan:

1. SlotSchema: slot nào cần HỎI KHÁCH HÀNG cho từng category (Module 1).
2. RangeSlotConfig: slot đó khớp với TRƯỜNG NÀO trong `spec` của sản phẩm
   và khớp bằng cách nào (Module 2 lọc, Module 3 chấm điểm).

Tách biệt 2 khái niệm này vì "budget_max" luôn là slot hỏi khách, nhưng
"room_area_m2" chỉ áp dụng cho air_conditioner, "household_size" áp dụng
cho refrigerator/washing_machine/dryer với TÊN SLOT GIỐNG NHAU nhưng field
nguồn trong spec khác nhau tuỳ category — cấu hình hoá để không phải viết
lại hàm riêng cho từng category (đây chính là điểm sửa so với bản Node cũ,
nơi category lạ bị rơi vào nhánh ranking của máy lạnh).

QUAN TRỌNG về RangeSlotConfig:
- Chỉ thêm RangeSlotConfig khi spec field tương ứng CÓ THỰC trong data
  (coverage ≥ 80%, xem docs/catalog_mapping_report.md).
- Không bịa spec field không tồn tại trong products_detail.json.
- Nếu spec field là TEXT (vd "8 kg", "100 lít"), dùng kind="text_number_tolerance"
  để parse_number() trích số từ chuỗi rồi so sánh với giá trị khách yêu cầu.
- tolerance_lo/hi mặc định 0.7/1.5 cho phép ±30%–50% để lọc không quá cứng.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RangeKind = Literal["two_field", "text_range", "text_number_tolerance"]


@dataclass(frozen=True)
class RangeSlotConfig:
    slot_name: str
    kind: RangeKind
    # two_field: (min_spec_key, max_spec_key) — đã có sẵn 2 field số trong spec
    min_spec_key: str | None = None
    max_spec_key: str | None = None
    # text_range: 1 field string dạng "X - Y đơn vị", parse_range_generic lúc truy vấn
    spec_key: str | None = None
    # text_number_tolerance: 1 field string chỉ có 1 con số (vd dung tích),
    # coi là khớp nếu giá trị khách yêu cầu nằm trong [value*lo, value*hi]
    tolerance_lo: float = 0.7
    tolerance_hi: float = 1.5
    label: str = ""


@dataclass(frozen=True)
class SlotSchema:
    required: list[str]
    optional: list[str] = field(default_factory=list)
    range_slots: list[RangeSlotConfig] = field(default_factory=list)


# Slot chung cho MỌI category (không riêng ngành nào) — "brand" (thương
# hiệu ưu tiên, vd "Panasonic") là field CÓ THẬT trong dữ liệu sản phẩm
# (product["brand"]) nên lọc được an toàn, không phải suy diễn/bịa thông số.
_COMMON_OPTIONAL_SLOTS = ["budget_min", "brand"]

_DEFAULT_SCHEMA = SlotSchema(
    required=["category", "budget_max"],
    # battery_priority/portability_priority/use_case: soft preference định
    # tính (vd "pin trâu", "mỏng nhẹ", "để đi học") — áp dụng chung cho mọi
    # category chưa có schema riêng (laptop, tablet, smartphone...), KHÔNG
    # bắt buộc hỏi, chỉ lưu lại nếu khách tự nhắc tới.
    optional=[*_COMMON_OPTIONAL_SLOTS, "battery_priority", "portability_priority", "use_case"],
)

# ---------------------------------------------------------------------------
# CATEGORY_SLOT_SCHEMAS — đủ 11 category thực trong DMX (14 ngành trong
# registry.json → 11 category DMX thực, vì một số gộp lại).
#
# Slug dùng phải khớp chính xác slug DMX thực tế (từ dmx_registry.json),
# không dùng slug cũ của registry.json (Excel).
#
# RangeSlotConfig chỉ được thêm khi spec field:
#   1. Thực sự tồn tại trong products_detail.json (coverage ≥ 80%)
#   2. Có thể parse thành số (qua parse_number hoặc parse_range_generic)
#   3. Có nghĩa với giá trị mà khách hàng thường cung cấp
#
# Nguồn: docs/catalog_mapping_report.md (thống kê thực tế)
# ---------------------------------------------------------------------------

CATEGORY_SLOT_SCHEMAS: dict[str, SlotSchema] = {
    # -------------------------------------------------------------------------
    # Máy lạnh — category duy nhất có two_field (area_min_m2 + area_max_m2)
    # vì DMX đã parse sẵn 2 field số; các category khác dùng text_number_tolerance.
    # -------------------------------------------------------------------------
    "air_conditioner": SlotSchema(
        required=["category", "budget_max", "room_area_m2", "installation_location"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "noise_priority", "power_saving_priority", "sun_exposure"],
        range_slots=[
            RangeSlotConfig(
                slot_name="room_area_m2",
                kind="two_field",
                min_spec_key="area_min_m2",
                max_spec_key="area_max_m2",
                label="diện tích phòng",
            ),
        ],
    ),

    # -------------------------------------------------------------------------
    # Tủ lạnh — capacity_liters (Dung tích sử dụng, 100% coverage)
    # Slot household_size → ánh xạ gần đúng sang capacity_liters trong spec
    # (hộ 4 người ~250-350L, hộ 2 người ~150-200L).
    # -------------------------------------------------------------------------
    "tu_lanh": SlotSchema(
        required=["category", "budget_max", "household_size"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "power_saving_priority"],
        range_slots=[
            RangeSlotConfig(
                slot_name="capacity_liters",
                kind="text_number_tolerance",
                spec_key="capacity_liters",
                tolerance_lo=0.65,
                tolerance_hi=1.5,
                label="dung tích tủ lạnh (lít)",
            ),
        ],
    ),

    # -------------------------------------------------------------------------
    # Máy giặt — wash_capacity_kg (Khối lượng giặt, 98% coverage)
    # household_size → proxy cho khối lượng (2-3 người ~7kg, 4+ người ~9-10kg)
    # -------------------------------------------------------------------------
    "may_giat": SlotSchema(
        required=["category", "budget_max", "household_size"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "power_saving_priority"],
        range_slots=[
            RangeSlotConfig(
                slot_name="wash_capacity_kg",
                kind="text_number_tolerance",
                spec_key="wash_capacity_kg",
                tolerance_lo=0.8,
                tolerance_hi=1.3,
                label="khối lượng giặt (kg)",
            ),
        ],
    ),

    # -------------------------------------------------------------------------
    # Máy sấy quần áo — dry_capacity_kg (Khối lượng sấy, 100% coverage)
    # -------------------------------------------------------------------------
    "may_say_quan_ao": SlotSchema(
        required=["category", "budget_max", "household_size"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "power_saving_priority"],
        range_slots=[
            RangeSlotConfig(
                slot_name="dry_capacity_kg",
                kind="text_number_tolerance",
                spec_key="dry_capacity_kg",
                tolerance_lo=0.8,
                tolerance_hi=1.3,
                label="khối lượng sấy (kg)",
            ),
        ],
    ),

    # -------------------------------------------------------------------------
    # Máy rửa chén — capacity_sets (Số chén bát rửa được, 100% coverage)
    # household_size → proxy cho số bộ chén (hộ 4 người ~9-12 bộ)
    # -------------------------------------------------------------------------
    "may_rua_chen": SlotSchema(
        required=["category", "budget_max", "household_size"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "noise_priority"],
        range_slots=[
            RangeSlotConfig(
                slot_name="capacity_sets",
                kind="text_number_tolerance",
                spec_key="capacity_sets",
                tolerance_lo=0.7,
                tolerance_hi=1.5,
                label="số bộ chén bát",
            ),
        ],
    ),

    # -------------------------------------------------------------------------
    # Tủ đông, tủ mát — capacity_liters (Dung tích sử dụng, 100% coverage)
    # Tên category thực trong JSON: "Tủ đông, tủ mát" (không phải "Tủ mát, tủ đông")
    # -------------------------------------------------------------------------
    "tu_dong_tu_mat": SlotSchema(
        required=["category", "budget_max", "capacity_liters"],
        optional=[*_COMMON_OPTIONAL_SLOTS],
        range_slots=[
            RangeSlotConfig(
                slot_name="capacity_liters",
                kind="text_number_tolerance",
                spec_key="capacity_liters",
                tolerance_lo=0.65,
                tolerance_hi=1.5,
                label="dung tích (lít)",
            ),
        ],
    ),

    # -------------------------------------------------------------------------
    # Máy nước nóng — tank_liters (Dung tích bình chứa, 100% coverage)
    # household_size → proxy cho dung tích (hộ 4 người ~20-30L)
    # -------------------------------------------------------------------------
    "may_nuoc_nong": SlotSchema(
        required=["category", "budget_max", "household_size"],
        optional=[*_COMMON_OPTIONAL_SLOTS],
        range_slots=[
            RangeSlotConfig(
                slot_name="tank_liters",
                kind="text_number_tolerance",
                spec_key="tank_liters",
                tolerance_lo=0.6,
                tolerance_hi=1.6,
                label="dung tích bình chứa (lít)",
            ),
        ],
    ),

    # -------------------------------------------------------------------------
    # Micro (karaoke + thu âm điện thoại gộp) — không có spec số đủ chắc
    # để lọc range. Chỉ dùng ngân sách + thương hiệu + portability_priority
    # (để phân biệt micro có dây vs không dây).
    # -------------------------------------------------------------------------
    "micro": SlotSchema(
        required=["category", "budget_max", "portability_priority"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "use_case"],
    ),

    # -------------------------------------------------------------------------
    # Đồng hồ thông minh — không có spec số parse được chắc chắn
    # (battery_life là text "7 ngày", không phải số mAh đồng nhất).
    # Dùng ngân sách + battery_priority làm filter chính.
    # -------------------------------------------------------------------------
    "dong_ho_thong_minh": SlotSchema(
        required=["category", "budget_max", "battery_priority"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "use_case"],
    ),

    # -------------------------------------------------------------------------
    # Máy tính bảng — RAM/storage là text ("8 GB", "256 GB"), không parse
    # số được nhất quán. Dùng ngân sách + battery_priority + portability.
    # -------------------------------------------------------------------------
    "may_tinh_bang": SlotSchema(
        required=["category", "budget_max", "battery_priority", "portability_priority"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "use_case"],
    ),

    # -------------------------------------------------------------------------
    # Pc, máy in (gộp desktop + màn hình + máy in) — use_case là slot bắt buộc
    # để phân biệt sub-type (monitor/desktop/printer). Không có spec range số
    # đồng nhất across sub-types.
    # -------------------------------------------------------------------------
    "pc_may_in": SlotSchema(
        required=["category", "budget_max", "use_case"],
        optional=[*_COMMON_OPTIONAL_SLOTS, "portability_priority"],
    ),

    "default": _DEFAULT_SCHEMA,
}


def get_slot_schema(category: str | None) -> SlotSchema:
    if category and category in CATEGORY_SLOT_SCHEMAS:
        return CATEGORY_SLOT_SCHEMAS[category]
    return _DEFAULT_SCHEMA
