"""
catalog/parse_specs.py — parse các cột Excel dạng chuỗi tiếng Việt không
đồng nhất thành giá trị có cấu trúc. KHÔNG suy diễn: parse thất bại -> None,
không đoán giá trị mặc định (đúng nguyên tắc chống hallucination).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_NO_DATA_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [r"^không$", r"cập nhật", r"^n/?a$"]]
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


def is_no_data_text(text: str | None) -> bool:
    if not isinstance(text, str):
        return True
    s = text.strip()
    if not s:
        return True
    return any(p.search(s) for p in _NO_DATA_PATTERNS)


@dataclass(frozen=True)
class Range:
    min: float
    max: float | None  # None = mở, không giới hạn trên

    def contains(self, value: float) -> bool:
        if value < self.min:
            return False
        if self.max is not None and value > self.max:
            return False
        return True


def parse_number(text) -> float | None:
    """Số đầu tiên tìm thấy trong chuỗi, coi '.' là phân cách hàng nghìn nếu
    theo sau bởi đúng 3 chữ số (định dạng số Việt Nam: "9.000" = 9000)."""
    if isinstance(text, (int, float)):
        return float(text)
    if not isinstance(text, str) or is_no_data_text(text):
        return None
    s = text.strip()
    # Số kiểu Việt Nam: nhóm chữ số cách nhau bởi dấu chấm, có thể có phần thập phân bằng dấu phẩy
    m = re.search(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    raw = m.group(0)
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", raw):
        # "9.000" hoặc "9.000,5" -> bỏ dấu chấm hàng nghìn, dấu phẩy là thập phân
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_range_generic(text) -> Range | None:
    """
    "Từ 30 - 40m² (từ 80 đến 120m³)" -> Range(30, 40)
    "Dưới 15m² (...)"                -> Range(0, 15)
    "Trên 5 người"                    -> Range(5, None)
    "3 - 4 người"                     -> Range(3, 4)
    "2 cánh"                          -> Range(2, 2)
    "Không" / "Đang cập nhật" / None  -> None
    """
    if not isinstance(text, str) or is_no_data_text(text):
        return None
    main_text = text.split("(")[0]
    lower = main_text.lower()
    numbers = [float(n.replace(",", ".")) for n in _NUMBER_RE.findall(main_text)]
    if not numbers:
        return None
    if "dưới" in lower:
        return Range(0, numbers[0])
    if "trên" in lower:
        return Range(numbers[0], None)
    if len(numbers) == 1:
        return Range(numbers[0], numbers[0])
    return Range(numbers[0], numbers[1])


def parse_boolean_vn(text, true_values: tuple[str, ...] = ()) -> bool | None:
    if not isinstance(text, str) or not text.strip():
        return None
    s = text.strip().lower()
    if s in ("có", "co", "yes", "true"):
        return True
    if s in ("không", "khong", "no", "false"):
        return False
    if is_no_data_text(text):
        return None
    for tv in true_values:
        if tv.lower() in s:
            return True
    return None


def parse_year(text) -> int | None:
    if not isinstance(text, str) or is_no_data_text(text):
        return None
    m = re.search(r"(19|20)\d{2}", text)
    return int(m.group(0)) if m else None


def parse_star_rating(text) -> int | None:
    """'5 sao (Hiệu suất năng lượng 6.23)' -> 5"""
    if not isinstance(text, str) or is_no_data_text(text):
        return None
    m = re.search(r"(\d+)\s*sao", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_efficiency_index(text) -> float | None:
    """'5 sao (Hiệu suất năng lượng 6.23)' -> 6.23"""
    if not isinstance(text, str) or is_no_data_text(text):
        return None
    m = re.search(r"hiệu suất năng lượng\s*([\d.,]+)", text, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def parse_inverter(text) -> bool | None:
    """'Máy lạnh Inverter' -> True, 'Máy lạnh không Inverter' -> False."""
    if not isinstance(text, str) or is_no_data_text(text):
        return None
    lower = text.lower()
    if "không inverter" in lower or "non-inverter" in lower or "non inverter" in lower:
        return False
    if "inverter" in lower:
        return True
    return None


@dataclass(frozen=True)
class NoiseReading:
    indoor_min_db: float | None
    indoor_max_db: float | None
    outdoor_db: float | None


def parse_noise_reading(text) -> NoiseReading:
    """
    'Dàn lạnh: 45/34/29 dB - Dàn nóng: 51 dB' -> indoor(29,45), outdoor 51
    Không có marker 'Dàn lạnh/Dàn nóng' -> coi số cuối cùng là dàn nóng
    (thường liệt kê sau), các số còn lại là dàn lạnh. Chỉ 1 số -> indoor only.
    """
    if not isinstance(text, str) or is_no_data_text(text):
        return NoiseReading(None, None, None)

    lower = text.lower()
    if "dàn lạnh" in lower and "dàn nóng" in lower:
        indoor_part, outdoor_part = re.split(r"dàn nóng", text, flags=re.IGNORECASE)
        indoor_nums = [float(n) for n in _NUMBER_RE.findall(indoor_part)]
        outdoor_nums = [float(n) for n in _NUMBER_RE.findall(outdoor_part)]
        indoor_min = min(indoor_nums) if indoor_nums else None
        indoor_max = max(indoor_nums) if indoor_nums else None
        outdoor = outdoor_nums[0] if outdoor_nums else None
        return NoiseReading(indoor_min, indoor_max, outdoor)

    numbers = [float(n) for n in _NUMBER_RE.findall(text)]
    if not numbers:
        return NoiseReading(None, None, None)
    if len(numbers) == 1:
        return NoiseReading(numbers[0], numbers[0], None)
    *indoor_nums, outdoor = numbers
    return NoiseReading(min(indoor_nums), max(indoor_nums), outdoor)


def parse_list_column(value) -> list[str]:
    """Cột kiểu 'list' trong registry — Excel thường lưu dạng chuỗi phân
    tách bởi dấu phẩy/chấm phẩy/xuống dòng."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if not isinstance(value, str) or is_no_data_text(value):
        return []
    parts = re.split(r"[;,\n]|,\s*", value)
    return [p.strip() for p in parts if p.strip()]


def parse_btu(raw) -> int | None:
    """'2.5 HP - 24000 BTU' -> 24000 (không lấy nhầm số HP '2.5' đứng trước).
    Tìm đúng số liền trước nhãn 'BTU', chấp nhận cả dạng có dấu chấm phân
    cách hàng nghìn ('24.000 BTU')."""
    if not isinstance(raw, str) or is_no_data_text(raw):
        return None
    m = re.search(r"([\d.,]+)\s*BTU", raw, re.IGNORECASE)
    if not m:
        return None
    return int(round(parse_number(m.group(1)) or 0)) or None


def effective_price(original_price, promotion_price) -> int | None:
    """Ưu tiên giá khuyến mãi nếu > 0, fallback giá gốc. Không bịa giá nếu
    cả hai đều thiếu."""
    if isinstance(promotion_price, (int, float)) and promotion_price and promotion_price > 0:
        return int(promotion_price)
    if isinstance(original_price, (int, float)) and original_price and original_price > 0:
        return int(original_price)
    return None


def price_to_int(raw) -> int | None:
    """Chuẩn hoá field giá của DMX (thường đã là số, đôi khi là chuỗi có
    dấu phân cách hàng nghìn) — KHÔNG bịa giá nếu parse thất bại."""
    if isinstance(raw, (int, float)) and not is_no_data_text(str(raw)):
        return int(raw)
    n = parse_number(raw)
    return int(n) if n is not None else None


def parse_kwh(raw) -> float | None:
    """'2.05 kWh' -> 2.05"""
    return parse_number(raw)


def parse_quantity_sold(raw) -> int | None:
    """DMX: '14,5k' -> 14500 ; '292' -> 292 ; None/'Không' -> None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if not isinstance(raw, str) or is_no_data_text(raw):
        return None
    s = raw.strip().lower()
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*k$", s)
    if m:
        return round(float(m.group(1).replace(",", ".")) * 1000)
    m = re.match(r"^\d+$", s)
    if m:
        return int(s)
    return None


def parse_rating(raw) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    return parse_number(raw)


def clean_str(raw) -> str | None:
    """Passthrough có làm sạch — dùng cho field không cần parse số/range."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    return None if is_no_data_text(s) else s


import unicodedata


def slugify_category_name(name: str) -> str:
    """'Tủ mát, tủ đông' -> 'tu_mat_tu_dong' — dùng làm category slug khi
    dmx_registry.json chưa khai báo slug tường minh cho category đó (hiện
    tại DMX mới map chi tiết cho 'Máy lạnh'; 118 category còn lại vẫn cần
    1 slug ổn định để làm key trong catalog dict, dù chỉ chạy ở mức lọc
    theo ngân sách cho tới khi có spec_map riêng).

    Dùng NFD decomposition (chuẩn Unicode) để bóc dấu thay vì bảng ký tự
    liệt kê thủ công — an toàn hơn, không sợ thiếu/sai ký tự.
    """
    nfd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfd if not unicodedata.combining(c))
    ascii_name = ascii_name.replace("đ", "d").replace("Đ", "D")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower()
    return slug or "unknown_category"
