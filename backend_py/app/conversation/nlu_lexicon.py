"""
conversation/nlu_lexicon.py — tập trung toàn bộ text normalization, alias
category, lỗi chính tả, từ viết tắt, cách nói ngân sách và soft preference
mà trước đây rải rác trong `canonicalize.py` và `_basic_parse()` của
`server.py`.

Nguyên tắc:
  - Chuẩn hoá (Unicode NFC, chữ thường, khoảng trắng, bản không dấu để so
    khớp mờ) chỉ dùng NỘI BỘ để match — KHÔNG BAO GIỜ ghi đè/làm mất raw
    user message gốc (caller luôn giữ nguyên `message` gốc để log/đưa vào
    prompt LLM).
  - Category suy ra được PHẢI xác thực lại với danh sách category THẬT
    trong catalog trước khi chấp nhận (tránh bịa category không tồn tại,
    và tránh gộp nhầm category gần nhau như "Tủ mát" / "Tủ lạnh" — fuzzy
    match CHỈ áp dụng trên từ vựng alias đã curate sẵn, KHÔNG áp dụng trực
    tiếp giữa các tên category thật với nhau).
  - Soft preference (`battery_priority`, `portability_priority`, `use_case`)
    chỉ là tín hiệu định tính lưu lại — không suy diễn thành số liệu cụ thể
    (vd không tự bịa dung lượng pin/thời lượng pin từ "pin trâu").
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache

# ---------------------------------------------------------------------------
# Chuẩn hoá text
# ---------------------------------------------------------------------------


def normalize_text(raw: str | None) -> str:
    """NFC + chữ thường + gộp khoảng trắng. Dùng để so khớp, KHÔNG dùng để
    thay thế raw message gốc ở bất kỳ đâu khác."""
    if not isinstance(raw, str):
        return ""
    s = unicodedata.normalize("NFC", raw).strip().lower()
    return re.sub(r"\s+", " ", s)


def strip_diacritics(s: str) -> str:
    """'điều hòa' -> 'dieu hoa' — dùng cho so khớp bản không dấu."""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_s = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_s.replace("đ", "d")


# ---------------------------------------------------------------------------
# Category alias
#
# Có 2 lớp:
#   1. Alias TỰ SINH từ toàn bộ category thật trong products_detail.json.
#      Nhờ vậy khi catalog có thêm/bớt category, không phải sửa file này.
#   2. Alias THỦ CÔNG bên dưới chỉ dành cho tiếng lóng, viết tắt, từ đồng
#      nghĩa và lỗi chính tả phổ biến mà tên category thật không thể bao phủ.
#
# Fuzzy chỉ áp dụng trên lớp thủ công, KHÔNG fuzzy trực tiếp giữa toàn bộ tên
# category thật -> tránh gộp nhầm những category gần nhau.
# ---------------------------------------------------------------------------

CATEGORY_ALIAS_LEXICON: dict[str, str] = {
    # Tivi
    "tivi": "tivi",
    "ti vi": "tivi",
    "tv": "tivi",
    "television": "tivi",
    "smart tv": "tivi",
    "smart tivi": "tivi",
    "tivi thong minh": "tivi",
    "tivi thông minh": "tivi",
    # Điện thoại
    "dien thoai": "dien_thoai",
    "điện thoại": "dien_thoai",
    "đt": "dien_thoai",
    "dt": "dien_thoai",
    "smartphone": "dien_thoai",
    "phone": "dien_thoai",
    "iphone": "dien_thoai",
    "dien thoai thong minh": "dien_thoai",
    "điện thoại thông minh": "dien_thoai",
    # Laptop
    "lap top": "laptop",
    "laptop": "laptop",
    "laptob": "laptop",
    "labtop": "laptop",
    "may tinh xach tay": "laptop",
    "máy tính xách tay": "laptop",
    "notebook": "laptop",
    "macbook": "laptop",
    # Máy tính bảng
    "may tinh bang": "may_tinh_bang",
    "máy tính bảng": "may_tinh_bang",
    "tablet": "may_tinh_bang",
    "ipad": "may_tinh_bang",
    # Máy rửa chén/bát
    "may rua bat": "may_rua_chen",
    "máy rửa bát": "may_rua_chen",
    "may rua chen": "may_rua_chen",
    "máy rửa chén": "may_rua_chen",
    "dishwasher": "may_rua_chen",
    # Máy lạnh / điều hòa
    "may lanh": "air_conditioner",
    "máy lạnh": "air_conditioner",
    "dieu hoa": "air_conditioner",
    "điều hòa": "air_conditioner",
    "may dieu hoa": "air_conditioner",
    "máy điều hòa": "air_conditioner",
    "ac": "air_conditioner",
    "đh": "air_conditioner",
    "dh": "air_conditioner",
    "air conditioner": "air_conditioner",
    # Máy giặt
    "may giat": "may_giat",
    "máy giặt": "may_giat",
    "washing machine": "may_giat",
    # Tủ lạnh; TUYỆT ĐỐI không map "tủ mát" vào đây
    "tu lanh": "tu_lanh",
    "tủ lạnh": "tu_lanh",
    "fridge": "tu_lanh",
    "refrigerator": "tu_lanh",
    # Catalog gộp tủ đông/tủ mát trong cùng một category thật
    "tu dong": "tu_dong_tu_mat",
    "tủ đông": "tu_dong_tu_mat",
    "tu mat": "tu_dong_tu_mat",
    "tủ mát": "tu_dong_tu_mat",
    "freezer": "tu_dong_tu_mat",
    # Máy sấy: không khai báo alias "máy sấy" vì câu đó còn mơ hồ
    "may say quan ao": "may_say_quan_ao",
    "máy sấy quần áo": "may_say_quan_ao",
    "may say ao quan": "may_say_quan_ao",
    "máy sấy áo quần": "may_say_quan_ao",
    "may say do": "may_say_quan_ao",
    "máy sấy đồ": "may_say_quan_ao",
    "clothes dryer": "may_say_quan_ao",
    "may say giay": "may_say_giay",
    "máy sấy giày": "may_say_giay",
    # Hút bụi
    "may hut bui": "may_hut_bui_gia_dinh",
    "máy hút bụi": "may_hut_bui_gia_dinh",
    "vacuum": "may_hut_bui_gia_dinh",
    "vacuum cleaner": "may_hut_bui_gia_dinh",
    "robot hut bui": "may_hut_bui_gia_dinh",
    "robot hút bụi": "may_hut_bui_gia_dinh",
    # Thiết bị nhà bếp
    "noi com": "noi_com_dien",
    "nồi cơm": "noi_com_dien",
    "noi com dien": "noi_com_dien",
    "nồi cơm điện": "noi_com_dien",
    "rice cooker": "noi_com_dien",
    "lo vi song": "lo_vi_song",
    "lò vi sóng": "lo_vi_song",
    "microwave": "lo_vi_song",
    "bep tu": "bep_tu",
    "bếp từ": "bep_tu",
    "bep dien tu": "bep_tu",
    "bếp điện từ": "bep_tu",
    "bep ga": "bep_ga",
    "bếp ga": "bep_ga",
    "bep gas": "bep_ga",
    "bếp gas": "bep_ga",
    "may hut mui": "may_hut_mui",
    "máy hút mùi": "may_hut_mui",
    "may ep": "may_ep_trai_cay",
    "máy ép": "may_ep_trai_cay",
    "may ep trai cay": "may_ep_trai_cay",
    "máy ép trái cây": "may_ep_trai_cay",
    "juicer": "may_ep_trai_cay",
    "may xay sinh to": "may_xay_sinh_to",
    "máy xay sinh tố": "may_xay_sinh_to",
    "blender": "may_xay_sinh_to",
    "am sieu toc": "binh_dun_sieu_toc",
    "ấm siêu tốc": "binh_dun_sieu_toc",
    "am dun nuoc": "binh_dun_sieu_toc",
    "ấm đun nước": "binh_dun_sieu_toc",
    "kettle": "binh_dun_sieu_toc",
    # Quạt và nước nóng
    "quat": "quat_cac_loai",
    "quạt": "quat_cac_loai",
    "quat dien": "quat_cac_loai",
    "quạt điện": "quat_cac_loai",
    "fan": "quat_cac_loai",
    "binh nong lanh": "may_nuoc_nong",
    "bình nóng lạnh": "may_nuoc_nong",
    "water heater": "may_nuoc_nong",
    # Âm thanh và phụ kiện công nghệ
    "tai nghe": "loa_tai_nghe",
    "tai nghe không dây": "loa_tai_nghe",
    "headphone": "loa_tai_nghe",
    "headset": "loa_tai_nghe",
    "earphone": "loa_tai_nghe",
    "airpods": "loa_tai_nghe",
    "sac du phong": "sac_du_phong",
    "sạc dự phòng": "sac_du_phong",
    "pin du phong": "sac_du_phong",
    "pin dự phòng": "sac_du_phong",
    "power bank": "sac_du_phong",
    "smartwatch": "dong_ho_thong_minh",
    "smart watch": "dong_ho_thong_minh",
    "dong ho thong minh": "dong_ho_thong_minh",
    "đồng hồ thông minh": "dong_ho_thong_minh",
    "may in": "pc_may_in",
    "máy in": "pc_may_in",
    "printer": "pc_may_in",
    "desktop": "pc_may_in",
    "o cung ngoai": "o_cung_di_dong",
    "ổ cứng ngoài": "o_cung_di_dong",
    "external hard drive": "o_cung_di_dong",
    # Camera / game / đọc sách
    "cam": "camera",
    "camera an ninh": "camera",
    "camera giám sát": "camera",
    "drone": "flycam",
    "fly cam": "flycam",
    "console": "may_choi_game",
    "may game": "may_choi_game",
    "máy game": "may_choi_game",
    "ebook reader": "may_doc_sach",
    "kindle": "may_doc_sach",
}


def _alias_forms(raw: str) -> set[str]:
    """Sinh các dạng so khớp an toàn cho tên category/slug.

    Không tự ý xóa toàn bộ khoảng trắng (vd ``ti vi`` -> ``tivi``), vì kiểu
    biến đổi đó dễ sinh va chạm. Các trường hợp tách/ghép từ phổ biến được
    curate trong ``CATEGORY_ALIAS_LEXICON``.
    """
    normalized = normalize_text(raw)
    punctuation_as_space = re.sub(r"[^\w\s]", " ", normalized)
    punctuation_as_space = re.sub(r"\s+", " ", punctuation_as_space).strip()
    forms = {normalized, punctuation_as_space}
    forms.update(strip_diacritics(form) for form in tuple(forms))
    return {form for form in forms if form}


def build_category_alias_index(catalog: dict | None = None) -> dict[str, str]:
    """Tạo alias cho TOÀN BỘ category thật trong catalog rồi chồng alias
    thủ công lên trên.

    ``catalog`` có dạng ``{category_slug: [product, ...]}``. Alias tự sinh
    bị va chạm giữa hai category sẽ bị loại bỏ; alias thủ công luôn được ưu
    tiên vì đã được curate có chủ đích.
    """
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()

    for category_slug, products in (catalog or {}).items():
        if not isinstance(category_slug, str) or not category_slug:
            continue

        display_name = None
        if isinstance(products, list) and products and isinstance(products[0], dict):
            display_name = products[0].get("category_name_vn")

        raw_forms = {category_slug, category_slug.replace("_", " ")}
        if isinstance(display_name, str) and display_name.strip():
            raw_forms.add(display_name)

        for raw_form in raw_forms:
            for form in _alias_forms(raw_form):
                previous = aliases.get(form)
                if previous is not None and previous != category_slug:
                    ambiguous.add(form)
                else:
                    aliases[form] = category_slug

    # Không đoán alias tự sinh nếu nó trỏ được tới nhiều category.
    for form in ambiguous:
        aliases.pop(form, None)

    # Alias curate được quyền ghi đè alias tự sinh.
    for raw_alias, category_slug in CATEGORY_ALIAS_LEXICON.items():
        for form in _alias_forms(raw_alias):
            aliases[form] = category_slug

    return aliases


@lru_cache(maxsize=1)
def get_category_alias_index() -> dict[str, str]:
    """Lazy-load catalog để không đọc products_detail.json ngay lúc import.

    Nếu module được dùng độc lập trong unit test hoặc catalog chưa sẵn sàng,
    lớp alias thủ công vẫn hoạt động. Loader/catalog chính của ứng dụng vẫn
    chịu trách nhiệm báo lỗi dữ liệu ở luồng khởi động server.
    """
    try:
        from app.catalog.catalog_store import get_catalog

        catalog = get_catalog()
    except Exception:  # noqa: BLE001 - fallback có chủ đích cho NLU cô lập
        catalog = {}
    return build_category_alias_index(catalog)


def _alias_phrases_by_length() -> list[str]:
    # Cụm dài/đặc hiệu phải được xét trước cụm ngắn, vd "sạc dự phòng"
    # trước "sạc", "điều khiển tivi" trước "tivi".
    return sorted(get_category_alias_index().keys(), key=len, reverse=True)

_FUZZY_CUTOFF = 0.82  # khá cao — chỉ sửa lỗi chính tả gần đúng, không đoán bừa

# Các cụm này thiếu thông tin để chọn duy nhất một category. Không cho fuzzy
# ép chúng về một nhánh cụ thể; hội thoại phải hỏi người dùng làm rõ.
AMBIGUOUS_CATEGORY_PHRASES = {
    "máy sấy",       # quần áo / giày
    "máy lọc nước", # RO Hydrogen / điện giải / thiết bị lọc nước
    "máy tính",      # laptop / tablet / PC
    "bếp",           # bếp ga / từ / điện
    "đồng hồ",       # thông minh / thời trang
}


@lru_cache(maxsize=128)
def _is_ambiguous_category_phrase(phrase: str) -> bool:
    forms: set[str] = set()
    for raw in AMBIGUOUS_CATEGORY_PHRASES:
        forms.update(_alias_forms(raw))
    return normalize_text(phrase) in forms


def _fuzzy_alias_lookup(token_or_phrase: str) -> str | None:
    # Cố ý chỉ fuzzy trên dict curate thủ công, không fuzzy trên 119 tên
    # category thật để tránh những category gần nhau bị gộp nhầm.
    if _is_ambiguous_category_phrase(token_or_phrase):
        return None
    matches = difflib.get_close_matches(token_or_phrase, CATEGORY_ALIAS_LEXICON.keys(), n=1, cutoff=_FUZZY_CUTOFF)
    return CATEGORY_ALIAS_LEXICON[matches[0]] if matches else None


def _phrase_in_text(phrase: str, text: str) -> bool:
    """Khớp cụm alias theo RANH GIỚI TỪ (word boundary), không phải substring
    thô — tránh bug 'ac' (viết tắt máy lạnh) khớp nhầm vào giữa 'xác định'."""
    return re.search(rf"(?<![a-zA-Z0-9]){re.escape(phrase)}(?![a-zA-Z0-9])", text) is not None


def _candidate_from_alias_lexicon(normalized: str) -> str | None:
    """Khớp CHÍNH XÁC toàn chuỗi, rồi theo ranh giới từ, rồi fuzzy trong
    phạm vi từ vựng alias đã curate (KHÔNG fuzzy giữa các category thật)."""
    aliases = get_category_alias_index()
    alias_phrases = _alias_phrases_by_length()

    if normalized in aliases:
        return aliases[normalized]

    for phrase in alias_phrases:
        if _phrase_in_text(phrase, normalized):
            return aliases[phrase]

    no_diacritics = strip_diacritics(normalized)
    if no_diacritics != normalized:
        for phrase in alias_phrases:
            if _phrase_in_text(phrase, no_diacritics):
                return aliases[phrase]

    return _fuzzy_alias_lookup(normalized) or _fuzzy_alias_lookup(no_diacritics)


def resolve_category_value(raw: str | None, known_categories=None) -> str | None:
    """
    Chuẩn hoá 1 giá trị category thô (thường là output ngắn gọn của LLM,
    vd "lap top", "Tủ lạnh", "laptob") thành slug canonical.

    `known_categories`: iterable các slug THẬT sự tồn tại trong catalog.
    Nếu truyền vào, kết quả PHẢI nằm trong tập này mới được chấp nhận —
    tránh chấp nhận nhầm 1 chuỗi trông giống category nhưng không khớp sản
    phẩm nào thật.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    normalized = normalize_text(raw)

    candidate = _candidate_from_alias_lexicon(normalized)

    if candidate is None and re.match(r"^[a-z][a-z0-9_]*$", normalized):
        candidate = normalized  # đã trông như 1 slug canonical (vd LLM trả thẳng "air_conditioner")

    if candidate is None:
        from app.catalog.parse_specs import slugify_category_name

        slug = slugify_category_name(raw)
        candidate = slug if slug != "unknown_category" else None

    if candidate is None:
        return None
    if known_categories is not None:
        return candidate if candidate in known_categories else None
    return candidate


def find_category_in_message(message: str, known_categories=None) -> str | None:
    """Quét TOÀN BỘ câu tự nhiên (không chỉ 1 giá trị category ngắn) để tìm
    cụm alias xuất hiện ở bất kỳ đâu trong câu — dùng cho fallback tất định
    khi LLM lỗi/không khả dụng."""
    if not isinstance(message, str) or not message.strip():
        return None
    normalized = normalize_text(message)
    no_diacritics = strip_diacritics(normalized)
    aliases = get_category_alias_index()

    candidate = None
    for phrase in _alias_phrases_by_length():
        if _phrase_in_text(phrase, normalized) or _phrase_in_text(phrase, no_diacritics):
            candidate = aliases[phrase]
            break

    if candidate is None:
        # fuzzy theo từng "cụm từ" (1-3 từ liên tiếp) trong câu, tránh so
        # fuzzy nguyên câu dài (dễ khớp nhầm).
        tokens = normalized.split()
        for window in (1, 2, 3):
            for i in range(len(tokens) - window + 1):
                phrase = " ".join(tokens[i : i + window])
                hit = _fuzzy_alias_lookup(phrase)
                if hit:
                    candidate = hit
                    break
            if candidate:
                break

    if candidate is None:
        return None
    if known_categories is not None:
        return candidate if candidate in known_categories else None
    return candidate


# ---------------------------------------------------------------------------
# Thương hiệu (brand) — 2 lớp giống category:
#   1. Alias thủ công cho tên gọi tắt/tiếng lóng phổ biến (vd "pana").
#   2. Khớp trực tiếp với tên brand THẬT có trong catalog (vd "Samsung",
#      "LG") — không cần khai báo thủ công cho từng brand.
# ---------------------------------------------------------------------------

BRAND_ALIAS_LEXICON: dict[str, str] = {
    "pana": "Panasonic",
    "sam": "Samsung",
    "sam sung": "Samsung",
}


@lru_cache(maxsize=1)
def _known_brands() -> dict[str, str]:
    """{tên brand đã chuẩn hoá: tên brand THẬT trong catalog}. Lazy-load để
    không đọc products_detail.json ngay lúc import (giống get_category_alias_index)."""
    try:
        from app.catalog.catalog_store import get_catalog

        catalog = get_catalog()
    except Exception:  # noqa: BLE001 — fallback có chủ đích cho NLU cô lập
        catalog = {}

    brands: dict[str, str] = {}
    for products in (catalog or {}).values():
        if not isinstance(products, list):
            continue
        for product in products:
            if not isinstance(product, dict):
                continue
            brand = product.get("brand")
            if isinstance(brand, str) and brand.strip():
                brands[normalize_text(brand)] = brand
    return brands


def extract_brand_from_text(text: str | None) -> str | None:
    """Tìm thương hiệu khách nhắc tới trong câu — KHÔNG bịa brand không có
    thật trong catalog. Alias thủ công (vd "pana") được xét trước, sau đó
    khớp trực tiếp với tên brand thật (cụm dài hơn xét trước để tránh khớp
    nhầm 1 phần của brand khác)."""
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = normalize_text(text)
    no_diacritics = strip_diacritics(normalized)

    for alias, brand in sorted(BRAND_ALIAS_LEXICON.items(), key=lambda kv: -len(kv[0])):
        if _phrase_in_text(alias, normalized) or _phrase_in_text(strip_diacritics(alias), no_diacritics):
            return brand

    known = _known_brands()
    for normalized_brand, real_brand in sorted(known.items(), key=lambda kv: -len(kv[0])):
        if _phrase_in_text(normalized_brand, normalized) or _phrase_in_text(strip_diacritics(normalized_brand), no_diacritics):
            return real_brand

    return None


# ---------------------------------------------------------------------------
# Ngân sách — đơn vị chuẩn + cách nói dân dã
# ---------------------------------------------------------------------------

BUDGET_UNIT_MULTIPLIERS: dict[str, int] = {
    "k": 1_000,
    "nghin": 1_000,
    "ngan": 1_000,
    "tr": 1_000_000,
    "trieu": 1_000_000,
    "cu": 1_000_000,
    "chai": 1_000_000,
    "ty": 1_000_000_000,
}

_BUDGET_UNIT_PATTERN = "|".join(
    sorted((re.escape(unit) for unit in BUDGET_UNIT_MULTIPLIERS), key=len, reverse=True)
)
_BUDGET_UNIT_RE = re.compile(
    rf"(\d+(?:[.,]\d+)?)\s*({_BUDGET_UNIT_PATTERN})\b",
    re.IGNORECASE,
)
_BUDGET_BIG_NUMBER_RE = re.compile(r"\b(\d{5,})\b")


def parse_budget_phrase(text: str | None) -> int | None:
    """'15 củ' / '15tr' / '15 triệu' -> 15_000_000; '500k' -> 500_000.
    Không suy diễn nếu không có đơn vị/số rõ ràng."""
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = strip_diacritics(normalize_text(text))
    m = _BUDGET_UNIT_RE.search(normalized)
    if m:
        amount = float(m.group(1).replace(",", "."))
        multiplier = BUDGET_UNIT_MULTIPLIERS[m.group(2).lower()]
        return round(amount * multiplier)
    m = _BUDGET_BIG_NUMBER_RE.search(re.sub(r"[.,]", "", normalized))
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Soft preference — dict tiếng lóng/từ đồng nghĩa, chỉ lưu tín hiệu định tính
# "high", KHÔNG suy diễn số liệu cụ thể (dung lượng pin, thời lượng pin...).
# ---------------------------------------------------------------------------

SOFT_PREFERENCE_LEXICON: dict[str, dict[str, str]] = {
    # Pin
    "pin trâu": {"battery_priority": "high"},
    "pin khỏe": {"battery_priority": "high"},
    "pin lâu": {"battery_priority": "high"},
    "pin bền": {"battery_priority": "high"},
    "bền pin": {"battery_priority": "high"},
    "pin cả ngày": {"battery_priority": "high"},
    "thời lượng pin tốt": {"battery_priority": "high"},
    # Di chuyển
    "mỏng nhẹ": {"portability_priority": "high"},
    "gọn nhẹ": {"portability_priority": "high"},
    "dễ mang": {"portability_priority": "high"},
    "dễ di chuyển": {"portability_priority": "high"},
    "hay di chuyển": {"portability_priority": "high"},
    # Nhu cầu dùng
    "để đi học": {"use_case": "student"},
    "đi học": {"use_case": "student"},
    "học tập": {"use_case": "student"},
    "sinh viên": {"use_case": "student"},
    "học sinh": {"use_case": "student"},
    "gaming": {"use_case": "gaming"},
    "chơi game": {"use_case": "gaming"},
    "chiến game": {"use_case": "gaming"},
    "làm việc": {"use_case": "work"},
    "văn phòng": {"use_case": "work"},
    "công việc": {"use_case": "work"},
}

_BATTERY_PRIORITY_PHRASES = tuple(
    phrase for phrase, values in SOFT_PREFERENCE_LEXICON.items() if "battery_priority" in values
)
_PORTABILITY_PRIORITY_PHRASES = tuple(
    phrase for phrase, values in SOFT_PREFERENCE_LEXICON.items() if "portability_priority" in values
)
_USE_CASE_PHRASES = {
    phrase: values["use_case"]
    for phrase, values in SOFT_PREFERENCE_LEXICON.items()
    if "use_case" in values
}


def extract_soft_preferences(text: str | None) -> dict[str, str]:
    """Trả về tối đa 3 field: battery_priority/portability_priority/use_case
    (giá trị "high" hoặc enum use_case) nếu câu có nhắc tới — KHÔNG bịa số."""
    result: dict[str, str] = {}
    if not isinstance(text, str) or not text.strip():
        return result
    normalized = normalize_text(text)
    no_diacritics = strip_diacritics(normalized)

    for phrase, values in SOFT_PREFERENCE_LEXICON.items():
        phrase_no_diacritics = strip_diacritics(phrase)
        if phrase in normalized or phrase_no_diacritics in no_diacritics:
            result.update(values)

    return result


def normalize_priority_value(raw) -> str | None:
    """Chuẩn hoá giá trị battery_priority/portability_priority về đúng 1
    trong các mức đã định nghĩa ("high") — không tạo mức mới tự phát."""
    if raw is True:
        return "high"
    if not isinstance(raw, str):
        return None
    s = normalize_text(raw)
    if s in ("high", "cao"):
        return "high"
    no_diacritics = strip_diacritics(s)
    all_priority_phrases = _BATTERY_PRIORITY_PHRASES + _PORTABILITY_PRIORITY_PHRASES
    if any(p in s or strip_diacritics(p) in no_diacritics for p in all_priority_phrases):
        return "high"
    return None


def normalize_use_case_value(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    s = normalize_text(raw)
    if s in ("student", "gaming", "work"):
        return s
    no_diacritics = strip_diacritics(s)
    for phrase, use_case in _USE_CASE_PHRASES.items():
        if phrase in s or strip_diacritics(phrase) in no_diacritics:
            return use_case
    return None


# ---------------------------------------------------------------------------
# Các slot khác đã có sẵn regex trong _basic_parse cũ của server.py — chuyển
# vào đây để tập trung 1 chỗ, dùng chung cho fallback tất định.
# ---------------------------------------------------------------------------


def extract_room_area(text: str) -> str | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(m2|m²)", normalize_text(text))
    return m.group(0) if m else None


def extract_installation_location(text: str) -> str | None:
    normalized = normalize_text(text)
    if re.search(r"phòng ngủ|phong ngu", normalized):
        return "phòng ngủ"
    if re.search(r"phòng khách|phong khach", normalized):
        return "phòng khách"
    return None


def extract_household_size(text: str) -> str | None:
    m = re.search(r"(\d+)\s*người", normalize_text(text))
    return m.group(0) if m else None


# ---------------------------------------------------------------------------
# Câu trả lời NGẮN theo đúng slot đang được hỏi — vd sau câu hỏi "Gia đình
# mình khoảng mấy người sử dụng ạ?", khách chỉ gõ "4" (không có chữ "người"
# đi kèm) nên các hàm extract_* phía trên (yêu cầu đơn vị rõ ràng) sẽ không
# khớp. Các parser dưới đây CHỈ áp dụng khi biết chính xác `expected_slot`
# (slot vừa được hỏi ở lượt trước), tránh diễn giải nhầm số/chữ đứng một
# mình trong ngữ cảnh khác.
# ---------------------------------------------------------------------------


def _parse_bare_number(text: str) -> float | None:
    """Câu trả lời CHỈ gồm 1 số (có thể kèm đơn vị quen thuộc), vd "4",
    "18", "18m2", "300 lít" — không suy diễn nếu có thêm chữ khác lạ."""
    normalized = normalize_text(text)
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*(m2|m²|lít|lit|người|nguoi|cái|cai)?\.?$", normalized)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


_YES_PHRASES = ("có", "co", "yes", "y", "đúng", "dung", "đúng rồi", "dung roi", "ừ", "u", "ok", "được", "duoc", "cần", "can")
_NO_PHRASES = ("không", "khong", "no", "n", "ko", "khỏi", "khoi", "không cần", "khong can")


def _parse_bare_yes_no(text: str) -> bool | None:
    normalized = normalize_text(text)
    if normalized in _YES_PHRASES:
        return True
    if normalized in _NO_PHRASES:
        return False
    return None


def _short_answer_number_slot(canonical_key: str):
    def parser(text: str) -> dict:
        value = _parse_bare_number(text)
        return {canonical_key: value} if value is not None else {}

    return parser


def _short_answer_yes_no_slot(canonical_key: str):
    def parser(text: str) -> dict:
        value = _parse_bare_yes_no(text)
        return {canonical_key: value} if value is not None else {}

    return parser


def _short_answer_budget_slot(text: str) -> dict:
    """Trả lời ngắn cho câu hỏi ngân sách: số nhỏ (vd "15") hiểu theo đơn vị
    triệu (ngữ cảnh mua sắm điện máy phổ thông); số đã đủ lớn (>=5 chữ số,
    vd "15000000") giữ nguyên là VND — không đoán đơn vị cho câu tự do
    ngoài ngữ cảnh đang hỏi ngân sách."""
    value = _parse_bare_number(text)
    if value is None:
        return {}
    normalized_digits = re.sub(r"[.,]", "", normalize_text(text))
    if normalized_digits.isdigit() and len(normalized_digits) >= 5:
        return {"budget_max": value}
    return {"budget_max": round(value * 1_000_000)}


# Cấu hình dạng dict theo slot (không if/else) — dễ mở rộng khi thêm slot mới.
SLOT_SHORT_ANSWER_PARSERS: dict[str, Any] = {
    "household_size": _short_answer_number_slot("household_size"),
    "room_area_m2": _short_answer_number_slot("room_area_m2"),
    "capacity_liters": _short_answer_number_slot("capacity_liters"),
    "budget_max": _short_answer_budget_slot,
    "noise_priority": _short_answer_yes_no_slot("noise_priority"),
    "power_saving_priority": _short_answer_yes_no_slot("power_saving_priority"),
    "sun_exposure": _short_answer_yes_no_slot("sun_exposure"),
    "battery_priority": _short_answer_yes_no_slot("battery_priority"),
    "portability_priority": _short_answer_yes_no_slot("portability_priority"),
}


def parse_short_answer_for_slot(text: str, expected_slot: str | None) -> dict:
    """Diễn giải câu trả lời ngắn theo ĐÚNG slot đang được hỏi. Trả về {}
    nếu không khớp kiểu mong đợi (caller vẫn còn logic tổng quát khác để
    thử) — không đoán bừa khi không chắc chắn."""
    if not expected_slot or not isinstance(text, str) or not text.strip():
        return {}
    parser = SLOT_SHORT_ANSWER_PARSERS.get(expected_slot)
    if not parser:
        return {}
    return parser(text)


def parse_message_deterministic(message: str, known_categories=None, expected_slot: str | None = None) -> dict:
    """
    Fallback tất định (KHÔNG dùng LLM) khi lời gọi LLM NLU lỗi/timeout.
    Trả về JSON phẳng cùng schema với output LLM — LUÔN cố lấy được category
    + ngân sách + soft preference nếu có, KHÔNG bao giờ âm thầm trả về {}
    nếu câu thực sự chứa thông tin nhận diện được (tránh hỏi lặp category).

    `expected_slot`: slot vừa được hỏi ở lượt trước (nếu có) — dùng để diễn
    giải đúng câu trả lời NGẮN (vd "4" cho household_size, "có"/"không" cho
    slot ưu tiên) mà các hàm extract_* tổng quát phía trên không bắt được
    vì thiếu đơn vị/từ khoá đi kèm.
    """
    result: dict = {}

    category = find_category_in_message(message, known_categories=known_categories)
    if category:
        result["category"] = category

    budget = parse_budget_phrase(message)
    if budget is not None:
        result["budget_max"] = budget

    area = extract_room_area(message)
    if area:
        result["area"] = area

    location = extract_installation_location(message)
    if location:
        result["installation_location"] = location

    household = extract_household_size(message)
    if household:
        result["household"] = household

    brand = extract_brand_from_text(message)
    if brand:
        result["brand"] = brand

    result.update(extract_soft_preferences(message))

    # Câu trả lời ngắn theo đúng slot đang hỏi — chỉ điền vào field CHƯA có
    # kết quả từ các bước tổng quát ở trên (không ghi đè tín hiệu mạnh hơn).
    short_answer = parse_short_answer_for_slot(message, expected_slot)
    for key, value in short_answer.items():
        result.setdefault(key, value)

    return result
