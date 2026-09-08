"""Hai lưới TUÂN THỦ, chạy cùng chỗ với `chan_so_sai` - ngay trước khi sang TTS.

Khác với ba lưới số (`chan_so_sai` / `chan_lai_suat_bia` / `chan_tien_sai`): chúng
hỏi "con số này có căn cứ không", còn hai lưới ở đây hỏi "câu này có ĐƯỢC PHÉP nói
không" và "con số này đang gán cho AI". Con số đúng vẫn có thể sai chủ thể - đó
chính là lỗ hổng đã lọt.

Cả hai sinh ra từ bản diễn lại cuộc 08c0d3e0 (07-09-2026). Xem
`tests/test_chan_tuan_thu.py` cho nguyên văn hai câu hỏng và cách truy ra gốc.

VÌ SAO LÀ LƯỚI CHỨ KHÔNG PHẢI PROMPT: dự án đã thử dặn bằng prompt ba kiểu và
hỏng ba kiểu khác nhau (xem chú thích `prefill` trong `llm_service`). Với tư vấn
tài chính thì "phần lớn lượt sẽ đúng" không phải một bảo đảm.
"""
import re

# --- Lưới 1: chữ không được phép nói -------------------------------------

# Từ mà nhân viên ngân hàng TUYỆT ĐỐI không nói với khách. Không phải danh sách
# từ thô tục - đây là những từ hàm ý làm sai quy trình, và một câu duy nhất lọt
# ra là đủ thành bằng chứng chống lại chính ngân hàng.
#
# Mô hình sinh ra chúng khi tài liệu nói KHÔNG mà nó vẫn muốn giúp khách: cuộc
# 08c0d3e0 khách hỏi nợ xấu, tri thức sản phẩm ghi "Không có nợ xấu tại CIC" là
# điều kiện, và mô hình đáp "bên em vẫn có cách lách để anh/chị vay được".
#
# Khớp theo TỪ (có ranh giới hai đầu) chứ không phải chuỗi con: "lách" nằm trong
# một câu bình thường thì không sao, nhưng chặn theo chuỗi con là chặn oan cả
# những từ chứa nó. Có test canh (`test_khong_bat_nham_tu_chua_chuoi_con`).
TU_CAM: tuple[str, ...] = (
    "lách luật", "lách", "chạy hồ sơ", "chạy điểm", "làm giả", "khai khống",
    "khai gian", "bao đậu", "bao duyệt", "đi cửa sau", "chống lưng", "lo lót",
)

# Câu thay khi dính chữ cấm. Nói THẲNG là còn tuỳ hồ sơ, rồi mời trao đổi tiếp -
# đó là điều đúng và cũng là điều tài liệu thật sự cho phép nói.
CAU_THAY_TU_CAM = ("Dạ trường hợp này còn tuỳ hồ sơ cụ thể, "
                   "em xin phép trao đổi thêm với anh chị ạ.")

_RANH = r"(?:^|[\s,\.\!\?\:\;\"'\(\)])"
_TU_CAM_RE = re.compile(
    _RANH + "(" + "|".join(re.escape(t) for t in TU_CAM) + ")" + r"(?=$|[\s,\.\!\?\:\;\"'\(\)])",
    re.IGNORECASE)


def chan_tu_cam(text: str) -> tuple[str, str | None]:
    """Thay CẢ câu nếu nó chứa chữ cấm. Trả (văn bản, mô tả chỗ chặn hoặc None).

    Thay cả câu chứ không cắt riêng chữ: bỏ mỗi chữ "lách" khỏi "bên em vẫn có
    cách lách để anh chị vay được" ra một câu vẫn hứa hẹn đúng thứ không được
    hứa. Vấn đề nằm ở Ý, không nằm ở chữ.
    """
    m = _TU_CAM_RE.search(text or "")
    if not m:
        return text, None
    return CAU_THAY_TU_CAM, f"chữ cấm {m.group(1)!r}"


# --- Lưới 2: gán thu nhập cho khách khi khách chưa nói --------------------

# Câu KHẲNG ĐỊNH thu nhập của khách. Bắt theo chủ thể "anh/chị/mình" đứng cạnh
# từ chỉ thu nhập, kèm một con số.
#
# CỐ Ý KHÔNG bắt câu nói về ĐIỀU KIỆN sản phẩm ("điều kiện là có lương từ 5
# triệu trở lên") - câu đó không gán cho ai, và nó là thứ tài liệu cho phép nói.
# Phân biệt bằng chính chủ thể: có "anh/chị/mình" thì mới là gán.
_CHU_THE = r"(?:anh|chị|anh/chị|anh chị|mình)"
_THU_NHAP = r"(?:lương|thu nhập)"
_SO = r"\d+(?:[.,]\d+)?"
_GAN_RE = re.compile(
    # "anh/chị có lương ... 3.4"  |  "lương của anh/chị là 3.4"
    rf"(?:{_CHU_THE}\s+(?:có\s+)?{_THU_NHAP}[^.?!]{{0,30}}?{_SO}"
    rf"|{_THU_NHAP}\s+(?:của\s+)?{_CHU_THE}[^.?!]{{0,30}}?{_SO})",
    re.IGNORECASE)

CAU_HOI_THU_NHAP = ("Dạ anh chị cho em xin mức thu nhập hàng tháng "
                    "để em tư vấn hạn mức chính xác ạ?")


def chan_gan_thu_nhap(text: str, khach_da_noi: str = "") -> tuple[str, str | None]:
    """Chặn AI KHẲNG ĐỊNH thu nhập của khách khi khách chưa từng nêu con số đó.

    `khach_da_noi` là toàn bộ lời khách trong cuộc (nối lại), KHÔNG phải ngữ cảnh
    tài liệu. Đây là điểm mấu chốt: con số 3.4 CÓ trong tài liệu nên mọi lưới đối
    chiếu tài liệu đều cho qua. Thứ duy nhất bảo chứng được cho một câu về thu
    nhập của khách là chính lời khách.

    Ba trường hợp KHÔNG chặn, đều có test canh:
      - khách đã tự nêu đúng con số đó  (AI nhắc lại là đúng)
      - câu nói về ĐIỀU KIỆN sản phẩm, không gán cho ai
      - câu HỎI thu nhập (hỏi thì được, khẳng định thay khách mới là lỗi)

    Thay bằng câu HỎI chứ không phải "em xin phép kiểm tra lại": thứ còn thiếu ở
    đây đúng là con số của khách, hỏi thẳng là cách gỡ nhanh nhất và cũng là việc
    một tư vấn viên thật sẽ làm.
    """
    t = text or ""
    if "?" in t:
        return text, None
    m = _GAN_RE.search(t)
    if not m:
        return text, None
    # Con số khách tự nêu thì AI nhắc lại là đúng.
    so_trong_cau = set(re.findall(_SO, m.group(0)))
    so_khach_noi = set(re.findall(_SO, khach_da_noi or ""))
    if so_trong_cau and so_trong_cau <= so_khach_noi:
        return text, None
    return CAU_HOI_THU_NHAP, f"gán thu nhập cho khách ({m.group(0)[:40]!r})"
