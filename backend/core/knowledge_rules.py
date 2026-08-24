"""Luật soi tài liệu tri thức - thứ AI đọc để tư vấn.

Vì sao cần: viết sai cách thì KHÔNG có gì báo. Bot vẫn trả lời trôi chảy, chỉ là
trả lời bằng số của sản phẩm khác, hoặc bằng số mà không hàng rào nào kiểm được.
Lỗi chỉ lộ ra khi khách đã nghe nhầm.

Ba luật nặng nhất đều bắt nguồn từ chỗ khác trong hệ thống, KHÔNG phải quy ước
thẩm mỹ - sửa bên kia thì phải sửa ở đây:

  `chan_so_sai`  (pipeline/text_normalizer.py) chỉ chạy khi tài liệu có ĐÚNG MỘT
                 số thập phân. Nhiều số thì nó bỏ qua - "đoán bừa còn tệ hơn".
  `_ma_san_pham` (services/rag_service.py) neo lưới lọc sản phẩm theo TÊN FILE.
                 Đặt tên không khớp nội dung là lưới không bao giờ ăn.
  `cat_manh`     (services/rag_service.py) cắt theo ký tự, không biết markdown.
                 Bảng dài mất dòng tiêu đề, câu bị bẻ giữa từ.

Soi CẢNH BÁO chứ không chặn lưu: chặn người vận hành sửa lãi suất lúc gấp còn
tệ hơn để họ lưu một tài liệu chưa đẹp.
"""

import re
import unicodedata

from backend.pipeline.text_normalizer import _so_thap_phan_trong
from backend.services.rag_service import cat_manh

# Dấu vết bản cài mẫu. Lãi suất trong mấy file đó là số bịa để chạy thử.
_DAU_VET_MAU = ("ngân hàng abc", "ngan hang abc")

# Chữ đứng ngay trước một con số làm con số đó hết chắc chắn. Bot đọc nguyên
# văn cho khách, mà "lãi suất từ 7.9%" nghe qua điện thoại thành một lời hứa.
_MO_HO = ("từ", "khoảng", "lên đến", "lên tới", "tối đa", "tối thiểu", "tuỳ", "tùy")
_MO_HO_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _MO_HO) + r")\s+[\d]", re.IGNORECASE)


# Mẫu cấu trúc để người viết khỏi phải đoán. Chính mẫu này cũng phải sạch theo
# luật ở dưới - mẫu vi phạm luật mình dạy thì người dùng chép về là mắc lỗi ngay
# (có test khoá lại). Đáng chú ý: mẫu sản phẩm chỉ mang MỘT số thập phân, vì đó
# đúng là điều kiện để hàng rào `chan_so_sai` chạy được.
MAU = {
    "products": """# Vay Tiêu Dùng Tín Chấp

## Thông tin sản phẩm
- Lãi suất: 9.5%/năm cố định trong suốt thời hạn vay
- Hạn mức: 30 triệu đến 500 triệu đồng
- Thời hạn: 12 tháng, 24 tháng hoặc 36 tháng
- Thời gian giải ngân: 24 giờ sau khi duyệt hồ sơ

## Điều kiện
- Tuổi 22 đến 60
- Thu nhập 8 triệu đồng/tháng trở lên
- Không có nợ xấu tại CIC

## Hồ sơ
- Căn cước công dân
- Sao kê lương 3 tháng gần nhất
- Hợp đồng lao động

## Ưu đãi
- Miễn phí thẩm định hồ sơ
- Miễn phí trả nợ trước hạn sau 12 tháng
""",

    "faq": """# Câu hỏi thường gặp về vay vốn

## Hồ sơ và thủ tục

### Vay tín chấp cần giấy tờ gì?
Căn cước công dân, sao kê lương 3 tháng gần nhất và hợp đồng lao động.

### Bao lâu thì có kết quả?
Hồ sơ đủ giấy tờ thì có kết quả trong 24 giờ làm việc.

## Trả nợ

### Trả nợ trước hạn có mất phí không?
Sau 12 tháng đầu thì miễn phí. Trong 12 tháng đầu thu phí theo hợp đồng.

### Trả chậm thì sao?
Ngân hàng tính lãi phạt trên phần chưa thanh toán và ghi nhận vào CIC.
""",

    "chinh_sach": """# Chính sách xử lý hồ sơ

## Phạm vi áp dụng
Áp dụng cho toàn bộ hồ sơ vay cá nhân nhận từ ngày 01 tháng 01 năm 2026.

## Nguyên tắc
- Hồ sơ thiếu giấy tờ được giữ trong 30 ngày trước khi đóng
- Khách bị từ chối được nộp lại sau 6 tháng
- Mọi thay đổi lãi suất phải thông báo trước 15 ngày

## Trường hợp cần chuyển chuyên viên
- Khách hỏi sản phẩm ngoài danh mục đang tư vấn
- Khách yêu cầu mức lãi suất ngoài khung
- Hồ sơ có dấu hiệu bất thường về giấy tờ
""",
}


def _khong_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", s.replace("đ", "d")).strip("_")


def _tieu_de(noi_dung: str) -> str:
    for dong in noi_dung.splitlines():
        if dong.strip().startswith("# "):
            return dong.strip()[2:].strip()
    return ""


def cat_ngang_bang(doan: str) -> bool:
    """Mảnh có dòng bảng nhưng MẤT dòng tiêu đề.

    Cắt theo ký tự chặt bảng lãi suất làm đôi là chuyện thường. Nửa sau mất tên
    cột, AI đọc được số mà không biết số của cột nào.
    """
    dong = [d.strip() for d in doan.splitlines() if d.strip()]
    co_bang = any(d.startswith("|") for d in dong)
    co_tieu_de = any("-" in d and set(d) <= set("|-: ") for d in dong)
    return co_bang and not co_tieu_de


def bat_dau_giua_cau(doan: str) -> bool:
    """Mảnh mở đầu bằng nửa câu của mảnh trước - chỗ cắt rơi vào giữa ý.

    Số đứng đầu KHÔNG mặc nhiên là đầu ý: chỉ số thứ tự danh sách ("3." hay
    "3)") mới là. Bắt được trên máy thật - vay_tin_chap.md cắt ngay giữa "sao kê
    lương 3 tháng gần nhất", nửa sau mở đầu bằng "3 tháng gần nhất".
    """
    d = (doan or "").lstrip()
    if not d:
        return False
    if d[0] in "#-*|>([":
        return False
    if re.match(r"\d+[.)]\s", d):
        return False
    return d[0].islower() or d[0].isdigit()


def soi_manh(noi_dung: str) -> list[dict]:
    """Cắt thử đúng như RAG sẽ cắt, kèm cờ cho từng chỗ cắt hỏng."""
    return [{
        "stt": i,
        "doan": d,
        "so_chu": len(d),
        "cat_ngang_bang": cat_ngang_bang(d),
        "bat_dau_giua_cau": bat_dau_giua_cau(d),
    } for i, d in enumerate(cat_manh(noi_dung or ""), 1)]


def soi_tai_lieu(noi_dung: str, nhom: str = "products", ten: str = "") -> dict:
    """Soi một tài liệu.

    Trả `{"loi": [...], "canh_bao": [...]}`, mỗi mục là
    `{"ma", "chu", "goi_y"}`. `ma` để giao diện nhận dạng, `chu` nói vấn đề,
    `goi_y` nói cách sửa - báo lỗi mà không nói sửa thế nào thì người dùng đứng
    im.

      loi      : làm bot nói sai số cho khách
      canh_bao : làm AI đọc thiếu ngữ cảnh, vẫn dùng được
    """
    noi_dung = noi_dung or ""
    loi: list[dict] = []
    canh_bao: list[dict] = []

    # --- lỗi ---------------------------------------------------------------
    thap_phan = sorted(f"{a}.{b}" for a, b in _so_thap_phan_trong(noi_dung))
    if len(thap_phan) > 1:
        loi.append({
            "ma": "nhieu_so_thap_phan",
            "chu": f"Có {len(thap_phan)} số thập phân: {', '.join(thap_phan)}",
            "goi_y": "Hàng rào chặn mô hình đọc sai số chỉ chạy khi tài liệu có "
                     "đúng MỘT số thập phân. Tách mục ví dụ tính toán sang tài "
                     "liệu riêng, giữ lại một con số quan trọng nhất.",
        })

    thap = noi_dung.lower()
    if any(v in thap for v in _DAU_VET_MAU):
        loi.append({
            "ma": "du_lieu_mau",
            "chu": 'Còn tên "Ngân hàng ABC" của bản cài mẫu',
            "goi_y": "Lãi suất và hạn mức trong tài liệu mẫu là số bịa để chạy "
                     "thử. Thay bằng tên và số thật trước khi gọi khách.",
        })

    # --- cảnh báo ----------------------------------------------------------
    tieu_de = _tieu_de(noi_dung)
    if not tieu_de:
        canh_bao.append({
            "ma": "thieu_tieu_de",
            "chu": "Không có dòng tiêu đề mở đầu bằng `# `",
            "goi_y": "Thêm `# Tên sản phẩm` ở đầu file. Không có nó thì mảnh đầu "
                     "tiên không mang tên sản phẩm, AI đọc số mà không biết của ai.",
        })
    elif nhom == "products" and ten:
        ma_ten, ma_tieu_de = _khong_dau(ten), _khong_dau(tieu_de)
        if ma_ten not in ma_tieu_de and ma_tieu_de not in ma_ten:
            canh_bao.append({
                "ma": "ten_khong_khop",
                "chu": f'Tên file "{ten}" không khớp tiêu đề "{tieu_de}"',
                "goi_y": "Lưới lọc sản phẩm neo theo TÊN FILE, không đọc nội "
                         "dung. Tên lệch là lọc không bao giờ ăn, và bot có thể "
                         "đọc lãi suất sản phẩm khác cho khách.",
            })

    if _MO_HO_RE.search(noi_dung):
        thay = sorted({m.group(1).lower() for m in _MO_HO_RE.finditer(noi_dung)})
        canh_bao.append({
            "ma": "so_mo_ho",
            "chu": "Số đứng sau chữ không chắc chắn: " + ", ".join(f'"{t}"' for t in thay),
            "goi_y": "Bot đọc nguyên văn cho khách nghe. Ghi con số cụ thể, "
                     "hoặc nói rõ điều kiện đi kèm mức đó.",
        })

    manh = soi_manh(noi_dung)
    if any(m["cat_ngang_bang"] for m in manh):
        n = sum(1 for m in manh if m["cat_ngang_bang"])
        canh_bao.append({
            "ma": "bang_mat_tieu_de",
            "chu": f"{n} mảnh có bảng nhưng mất dòng tiêu đề sau khi cắt",
            "goi_y": "Tài liệu bị cắt theo số ký tự nên bảng dài bị chặt làm "
                     "đôi. Chia bảng thành nhiều bảng ngắn, mỗi bảng có tiêu đề "
                     "cột riêng.",
        })
    if any(m["bat_dau_giua_cau"] for m in manh):
        n = sum(1 for m in manh if m["bat_dau_giua_cau"])
        canh_bao.append({
            "ma": "cat_giua_y",
            "chu": f"{n} mảnh bắt đầu từ giữa câu",
            "goi_y": "Chỗ cắt rơi vào giữa ý. Thêm tiêu đề con `## ` để chia "
                     "tài liệu thành phần ngắn hơn.",
        })

    return {"loi": loi, "canh_bao": canh_bao}
