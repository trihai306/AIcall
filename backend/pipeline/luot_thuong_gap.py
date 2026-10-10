"""Trả lời sẵn cho những lượt KHÔNG phải câu hỏi sản phẩm.

Vì sao không để mô hình lo: đo bằng `scripts/do_tra_loi_mot_kieu.py` trên
`tuvan-qwen`:

    câu hỏi sản phẩm          0/4  rơi vào khuôn thoái thác
    lượt không phải câu hỏi   5/10 rơi vào khuôn

Mô hình trả lời câu sản phẩm rất chuẩn, nhưng gặp lượt chào hỏi / dò hỏi / từ
chối thì bịa ra một khuôn "xin lỗi ... ghi nhận ... chuyên viên liên hệ lại".
Có câu sai hẳn nghĩa: "ai đấy" -> *"bên em đang có chuyên viên liên hệ lại"*;
"gọi lại sau nhé" -> *"em cảm ơn anh chị đã GỌI"* (mình gọi cho khách chứ).

Gốc rễ nằm ở bộ dữ liệu: 284/284 mẫu đều là hỏi-đáp sản phẩm, không mẫu nào dạy
xử lý lượt còn lại - mà trong cuộc gọi thật đó mới là phần lớn. Sửa gốc là thêm
mẫu rồi train lại; trong lúc chờ thì chặn ở đây.

BA RÀNG BUỘC CỐ Ý, đừng nới:
  1. Chỉ nhận lượt NGẮN (<= `TOI_DA_TU` từ). Câu dài gần như luôn có nội dung
     thật, để mô hình lo.
  2. So trên bản BỎ DẤU, vì kênh thoại 8kHz làm mất thanh điệu trước tiên
     ("ai đấy" -> "ai đây", "a lô" -> "alo").
  3. Không khớp thì trả None, đi tiếp đường cũ. Bảng này chỉ được phép làm TỐT
     HƠN hiện trạng, không được phép chặn nhầm rồi làm tệ đi.

LỜI THOẠI DƯỚI ĐÂY LÀ BẢN NHÁP - người phụ trách nghiệp vụ phải duyệt, nhất là
câu trả lời "sao em có số của anh": nói sai chỗ đó là vấn đề pháp lý, không phải
vấn đề kỹ thuật.
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

TOI_DA_TU = 8

Y_DINH_TU_CHOI = "tu_choi"
Y_DINH_HEN_LAI = "hen_lai"
Y_DINH_DANG_BAN = "dang_ban"


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d")
    return re.sub(r"[^a-z0-9\s]+", " ", s).strip()


def _chuan(s: str) -> str:
    return re.sub(r"\s+", " ", bo_dau(s))


def _cac_ve(s: str) -> list[str]:
    """Chuẩn hóa nhưng giữ ranh giới mệnh đề cho suy luận attribution."""
    # Tách trước khi bỏ dấu để không biến dấu câu thành khoảng trắng và không
    # cho phủ định/chủ thể ở vế trước chi phối ứng viên thuộc vế sau.
    s = re.sub(r"[,.;:!?]+", " | ", (s or "").lower())
    s = re.sub(r"\b(?:nhưng|nhung|mà|ma)\b", " | nhung ", s)
    return [ve for ve in (_chuan(x) for x in s.split("|")) if ve]


_PHU_DINH_Y_DINH = re.compile(
    r"\b(?:khong phai|dau phai|khong he|dau co)\b.{0,38}$"
    r"|\b(?:khong|chua tung|chua bao gio)\s+(?:noi|bao|yeu cau|de nghi)\b.{0,38}$"
    r"|\bkhong\s+can\b.{0,24}$")
_NOI_VE_CAU_CHU = re.compile(
    r"(?:\b(?:cum|vi du|nhac lai|trich dan)\b|(?<!nhu )\bcau\b).{0,45}$"
    r"|\b(?:nghia la gi|co nghia gi|hieu sao)\b.{0,35}$")
_YEU_CAU_TIEP_TUC = re.compile(
    r"\b(?:nhung|ma|con|thi)\b.{0,35}\b(?:muon|can)\b.{0,22}"
    r"\b(?:vay(?=\b|\d)|lam\b|mo\b|dang ky\b|hoi\b|biet\b|nghe\b|tu van\b|noi\b)"
    r"|\b(?:nhung|ma|con|thi)\b.{0,35}\b(?:quan tam|co nhu cau)\b"
    r"|\b(?:nhung|ma|con|thi)\b.{0,35}\bcan(?=\d)"
    r"|\b(?:anh|chi|toi|tui|co|chu|bac|minh|chau|em)\s+(?:van\s+)?(?:muon|can)\b.{0,22}"
    r"\b(?:vay(?=\b|\d)|lam\b|mo\b|dang ky\b|hoi\b|biet\b|nghe\b|tu van\b|noi\b)"
    r"|\b(?:anh|chi|toi|tui|co|chu|bac|minh|chau|em)\s+(?:van\s+)?"
    r"(?:quan tam|co nhu cau)\b"
    r"|\b(?:cu|hay)\s+(?:tu van|noi|hoi)\b.{0,18}\b(?:tiep|di)\b"
    r"|\btiep tuc\s+(?:tu van|noi|hoi)\b"
    r"|\b(?:tu van|noi|hoi)\s+tiep(?:\s+di)?\b")
_HUY_TRANG_THAI_BAN = re.compile(
    r"\b(?:(?:anh|chi|toi|tui|co|chu|bac|minh|chau|em)\s+)?(?:gio\s+)?"
    r"(?:khong\s+con|khong|het)\s+(?:ban|lai xe|chay xe|di duong)(?:\s+nua)?\b")
_CHU_THE_NGUOI_KHAC = re.compile(
    r"\b(?:(?:vo|chong|bo|me|ba|con trai|con gai|sep|dong nghiep|nguoi nha|nguoi ta)"
    r"(?:\s+(?:anh|chi|toi|tui|co|chu|bac|em))?"
    r"|ban\s+(?:anh|chi|toi|tui|co|chu|bac|em))\b")
_CHU_THE_KHACH = re.compile(r"\b(?:anh|chi|toi|tui|co|chu|bac|minh|chau|em)\b")
_LOI_TU_CHOI = re.compile(
    r"\b(?:khong|chua)\s+(?:co\s+)?(?:nhu cau|quan tam)\b"
    r"|\bkhong\s+muon\s+vay(?:\b|(?=\d))"
    r"|\bkhong\s+vay(?:\s+(?:dau|gi))?\b"
    r"|\bkhong\s+thich(?:\s+nua)?\b"
    r"|\bchua\s+can\s+(?:vay|mo|lam|dang ky)\b"
    r"|\bkhong\s+can(?:\s+(?:vay|tu van|nghe|mo the|lam the))?(?:\s+(?:dau|nua))?(?:$|[.!?,])")
_DUNG_RO_RANG = re.compile(
    r"\b(?:dung|ngung)\s+(?:cuoc\s+goi|goi\s+(?:nua|lai|cho\s+(?:anh|chi|toi|tui|co|chu|bac|em))|"
    r"lien\s+he\s+(?:nua|lai))\b"
    r"|\b(?:dung|thoi)\s+(?:moi|doc|tu van|noi)\b.{0,45}\b(?:nua|tiep)\b"
    r"|\b(?:dung|thoi)\s+hoi(?:\s+(?:anh|chi|toi|tui|co|chu|bac|em))?\s+nua\b"
    r"|^\s*thoi(?:\s+(?:nhe|nha|em|di))?\s*$")
_HEN_LAI = re.compile(
    r"\b(?:goi|lien he)\s+lai\s+(?:sau|luc|vao|tam|mai|hom khac|khi khac|gio khac)\b"
    r"|\bgoi\s+(?:lai\s+)?(?:luc|vao|tam)\s*\d"
    r"|\bmai\s+(?:anh|chi|toi|tui|co|chu|bac|em)\s+goi\s+lai\b"
    r"|\bkhi nao\s+(?:ranh|can|tien)\b.{0,35}\b(?:goi|bao|lien he)\b"
    r"|\bnhan\s+tin\s+(?:cho|qua)\s+(?:anh|chi|toi|tui|co|chu|bac|em)\b"
    r"|\b(?:phai|de)\s+hoi\s+(?:vo|chong|bo|me|con|gia dinh|nguoi nha)\b"
    r"|\bde\s+(?:hom|ngay|buoi|luc)\s+khac\b"
    r"|\bde\s+(?:anh|chi|toi|tui|co|chu|bac|minh|em)\s+"
    r"(?:xem|nghi|suy nghi|tinh(?:\s+lai)?|hoi\s+(?:vo|chong|bo|me|con|gia dinh|nguoi nha))\b"
    r"|\bchua\s+quyet\s+dinh\b")
_DANG_BAN = re.compile(
    r"\b(?:dang\s+(?:ban|hop|lai xe|chay xe|di duong|di lam)|ban\s+(?:lam|qua|roi|viec|hop)|"
    r"hoi\s+ban|khong\s+(?:ranh|tien\s+(?:nghe|noi chuyen)))\b"
    r"|^\s*(?:anh|chi|toi|tui|co|chu|bac|em)?\s*ban\s*$")


def _la_y_dinh_cua_khach(t: str, m: re.Match[str], ten: str) -> bool:
    """Ứng viên điều khiển là lời trực tiếp của khách, không phải phủ định/trích dẫn."""
    truoc = t[max(0, m.start() - 60):m.start()]
    if _PHU_DINH_Y_DINH.search(truoc) or _NOI_VE_CAU_CHU.search(truoc):
        return False
    if ten == Y_DINH_HEN_LAI and re.search(r"\b(?:dung|ngung|khong)\s*$", truoc):
        # "đừng gọi lại sau" là cấm gọi, không phải một lịch hẹn.
        return False
    nguoi_khac = list(_CHU_THE_NGUOI_KHAC.finditer(truoc))
    khach = list(_CHU_THE_KHACH.finditer(truoc))
    if nguoi_khac and (not khach or nguoi_khac[-1].end() >= khach[-1].end()):
        return False
    if nguoi_khac:
        sau_nguoi_khac = truoc[nguoi_khac[-1].end():]
        if re.search(r"\b(?:bao|noi|muon|de nghi|yeu cau)\b", sau_nguoi_khac):
            # "vợ bảo tôi gọi lại" vẫn là ý của vợ dù chữ "tôi" đứng gần hơn.
            return False
    return True


def y_dinh_dung_tu_van(text: str) -> str | None:
    """Nhận diện điều khiển cuộc gọi, không phụ thuộc độ dài hay dấu tiếng Việt.

    Giá trị trả về dùng chung cho các tầng ưu tiên: ``tu_choi`` là dừng hẳn,
    ``hen_lai`` là khách hoãn/hẹn lại, ``dang_ban`` là đang bận và cần khép
    nhanh hoặc hỏi thời gian tiện. ``None`` nghĩa là tiếp tục phân luồng nội
    dung bình thường. Chỉ lời trực tiếp, không bị phủ định của chính khách mới
    có hiệu lực; nếu khách đổi ý trong cùng lượt thì ý trực tiếp sau cùng thắng.
    Riêng đang điều khiển phương tiện luôn trả ``dang_ban`` để khép nhanh.
    """
    cac_ve = _cac_ve(text)
    if not cac_ve:
        return None
    ung_vien: list[tuple[int, int, str, str, int]] = []
    tiep_tuc: list[int] = []
    huy_ban: list[int] = []
    # Số thứ hai chỉ phá hòa khi hai regex bắt cùng vị trí: dừng rõ ràng mạnh
    # hơn từ chối, hẹn lại, rồi mới đến trạng thái bận.
    vi_tri = 0
    for ve in cac_ve:
        for ten, uu_tien, mau in (
            (Y_DINH_TU_CHOI, 4, _DUNG_RO_RANG),
            (Y_DINH_TU_CHOI, 3, _LOI_TU_CHOI),
            (Y_DINH_HEN_LAI, 2, _HEN_LAI),
            (Y_DINH_DANG_BAN, 1, _DANG_BAN),
        ):
            for m in mau.finditer(ve):
                if _la_y_dinh_cua_khach(ve, m, ten):
                    ung_vien.append((vi_tri + m.start(), uu_tien, ten,
                                     m.group(0), vi_tri + m.end()))
        tiep_tuc.extend(
            vi_tri + m.start() for m in _YEU_CAU_TIEP_TUC.finditer(ve)
            if _la_y_dinh_cua_khach(ve, m, "tiep_tuc")
        )
        huy_ban.extend(
            vi_tri + m.start() for m in _HUY_TRANG_THAI_BAN.finditer(ve)
            if _la_y_dinh_cua_khach(ve, m, "tiep_tuc")
        )
        vi_tri += len(ve) + 1
    if not ung_vien:
        return None

    cuoi = max(ung_vien, key=lambda x: (x[0], x[1]))
    if (cuoi[2] == Y_DINH_DANG_BAN
            and huy_ban and max(huy_ban) >= cuoi[4]):
        return None
    if cuoi[2] == Y_DINH_DANG_BAN and re.search(
            r"\b(?:lai xe|chay xe|di duong)\b", cuoi[3]):
        # Đang điều khiển phương tiện luôn khép nhanh dù khách muốn nghe tiếp.
        return Y_DINH_DANG_BAN
    if tiep_tuc and max(tiep_tuc) >= cuoi[4]:
        return None

    # Hoãn để cân nhắc rồi "đừng hỏi nữa" vẫn là hoãn, không phải cấm liên hệ.
    if cuoi[2] == Y_DINH_TU_CHOI and re.match(r"(?:dung|thoi) hoi", cuoi[3]):
        hen_truoc = [x for x in ung_vien if x[2] == Y_DINH_HEN_LAI and x[0] < cuoi[0]]
        if hen_truoc:
            return Y_DINH_HEN_LAI
    return cuoi[2]


_HOI_AI = re.compile(
    r"\b(?:em|ban|chau)\s+(?:co phai\s+)(?:la\s+)?(?:ai|robot|may)\b"
    r"|\b(?:em|ban|chau)\s+(?:la\s+)?(?:robot|may|nguoi that)\b"
    r"|\b(?:ai|robot|may)\s+hay\s+(?:nguoi|nguoi that)\b"
    r"|\b(?:nguoi|nguoi that)\s+hay\s+(?:ai|robot|may)\b"
    r"|\b(?:dang noi chuyen|noi chuyen)\s+voi\s+(?:robot|may|nguoi that)\b")
_HOI_NGUON_SO = re.compile(
    r"\b(?:sao|tai sao)\s+(?:em|minh|ben em)?\s*(?:lai\s+)?co\s+(?:so|sdt)\b"
    r"|\b(?:so|sdt)\b.{0,30}\b(?:o dau ra|tu dau|nguon nao)\b"
    r"|\b(?:lay|co)\s+(?:so|sdt)\b.{0,25}\b(?:o dau|tu dau)\b"
    r"|\bai\s+cho\s+(?:so|sdt)\b")


def _y_dinh_danh_tinh_nguon(text: str) -> str | None:
    t = _chuan(text)
    hoi_ai = bool(_HOI_AI.search(t))
    hoi_nguon = bool(_HOI_NGUON_SO.search(t))
    if hoi_ai and hoi_nguon:
        return "danh_tinh_va_nguon"
    if hoi_ai:
        return "danh_tinh_tu_dong"
    if hoi_nguon:
        return "sao_co_so"
    return None


# (tên ý định, các mẫu nhận dạng, câu trả lời)
# Mẫu so bằng `re.search` trên chuỗi ĐÃ BỎ DẤU.
BANG = [
    ("danh_tinh_va_nguon", [],
     "Dạ em là trợ lý tư vấn tự động sử dụng AI của VoiceBankAI ạ. "
     "Em không có thông tin đã được xác minh về nguồn số điện thoại này; nếu "
     "anh chị không muốn được liên hệ tiếp, em xin phép ghi nhận ạ."),

    ("danh_tinh_tu_dong", [],
     "Dạ em là trợ lý tư vấn tự động sử dụng AI của VoiceBankAI ạ."),

    ("nghe_ro_khong",
     # Cố ý để khoảng giữa "co nghe" và "khong" tự do: kênh 8kHz cho phiên âm
     # sai chính giữa câu ("có nghe TIẾNG anh nói không" -> "có nghe THEO anh
     # nói không"). Liệt kê từng từ một là chắc chắn trượt. An toàn vì cả bảng
     # chỉ chạy trên lượt <= TOI_DA_TU từ.
     # Nhánh "nghe rõ" phải để khoảng tự do Y HỆT nhánh "có nghe" - trước chỉ
     # bắt "nghe rõ không" liền nhau nên cuộc gọi thật trượt câu "nghe rõ NHỮNG
     # GÌ ANH NÓI không", rồi LLM đọc thành lời từ chối và đáp "em xin lỗi đã
     # làm phiền ạ". Một câu hỏi thành một lời xin lỗi.
     [r"\bco nghe\b.{0,22}\bkhong\b", r"\bnghe (ro|thay|duoc)\b.{0,25}\bkhong\b",
      r"\bco ro khong\b", r"\bnghe ro chua\b",
      r"\bnghe\b.{0,20}\b(anh|chi|toi) noi khong\b"],
     "Dạ em nghe rõ ạ."),

    ("ai_day",
     [r"^\s*(alo\s+|a lo\s+)?ai (day|do|the|vay|goi)", r"\bai goi (day|do|vay)\b",
      r"\bem la ai\b", r"\bben nao (day|do|vay)\b", r"\bcong ty nao\b"],
     "Dạ em là {agent} bên {bank}, em gọi để giới thiệu chương trình {product} ạ."),

    ("ten_tu_van",
     # Tên tư vấn viên nằm ở kịch bản chứ không ở tài liệu nào, nên kho trả lời
     # không soạn sẵn được câu này và mô hình phải tự viết mỗi lần.
     [r"\bem ten (la )?gi\b", r"\bten em la gi\b", r"\bem la ban nao\b",
      r"\bcho (anh|chi|toi) (xin|hoi|biet) ten\b"],
     "Dạ em tên {agent}, tư vấn viên bên {bank} ạ."),

    ("sao_co_so",
     [r"\bsao (em |minh )?(lai )?co (so|sdt)", r"\b(so|sdt) .*o dau (ra|the|vay)",
      r"\blay so .*o dau\b", r"\bai cho (so|sdt)\b"],
     "Dạ em không có thông tin đã được xác minh về nguồn số điện thoại này ạ. "
     "Nếu anh chị không muốn được liên hệ tiếp, em xin phép ghi nhận ạ."),

    ("sao_biet_ten",
     [r"\bsao (em |minh )?(lai )?biet (ten )?(anh|chi|toi)\b",
      r"\bsao (lai )?goi (dung )?ten\b",
      r"\bsao em biet ca (anh|chi|toi)\b"],
     "Dạ hệ thống cuộc gọi có hiển thị tên để em xưng hô cho đúng ạ."),

    ("vi_tri_tu_van",
     [r"^\s*em (dang )?o dau( nhi|vay|the)?\s*$",
      r"^\s*(the )?em goi tu dau( vay|the)?\s*$"],
     "Dạ em đang hỗ trợ anh chị qua điện thoại từ {bank} ạ."),

    ("chua_ro_thong_tin",
     [r"^\s*tim ra chua\s*$"],
     "Dạ anh chị đang hỏi thông tin nào ạ?"),

    ("chua_ro_thoi_gian",
     [r"^\s*lau\s*$"],
     "Dạ anh chị đang hỏi khoảng thời gian nào ạ?"),

    ("chua_ro_nhu_cau",
     [r"^\s*em tu van giup (anh|chi|toi).{0,28}con vay ben (minh|em)\s*$"],
     "Dạ anh chị đang muốn hỏi về khoản vay mới hay khoản vay hiện tại ạ?"),

    ("moi_noi_tiep",
     [r"^\s*(u+|ok|okie|duoc|vang|roi)?\s*(thi |thoi )?em noi (di|xem)\b",
      r"^\s*noi (di|xem|nghe)\b", r"^\s*(u+|vang)\s*(noi )?(di|xem)\s*$",
      r"\bco (viec|chuyen) gi (khong|the|vay)\b", r"\bgoi co viec gi\b"],
     "Dạ bên em đang có chương trình {product} ưu đãi, em xin phép giới thiệu "
     "nhanh với anh chị ạ."),

    ("dang_ban",
     # Liệt kê từng cụm thay vì bắt trơ "ban": bỏ dấu rồi thì "bận", "bạn" và
     # "bàn" trùng nhau, bắt trơ là chặn nhầm "bạn anh cũng vay bên em".
     [r"\b(dang ban|ban lam|ban qua|ban roi|ban viec|hoi ban)\b",
      r"^\s*(anh|chi|toi|em)?\s*ban\s*$",
      r"\bkhong ranh\b", r"\bdang di lam\b", r"\bdang hop\b", r"\bdang lai xe\b"],
     "Dạ em xin lỗi đã gọi không đúng lúc ạ. Em xin phép gọi lại, "
     "khoảng mấy giờ thì tiện cho anh chị ạ?"),

    ("tu_choi",
     [r"\bkhong (co )?(quan tam|nhu cau|can)\b", r"\bkhong vay (dau|gi)?\b",
      r"^\s*thoi\s*(nhe|nha|em|di)?\s*$", r"\bdung goi (nua|lai)\b"],
     "Dạ em hiểu ạ. Em cảm ơn anh chị đã nghe máy, em xin phép không làm phiền "
     "thêm ạ."),

    ("hen_lai",
     [r"\bgoi lai (sau|sau nhe|gio khac|lan sau)\b", r"\bde (anh|chi|toi) xem\b",
      r"\bkhi nao (ranh|can) (thi )?(anh|chi|toi) (goi|bao)\b",
      r"\bmai (anh|chi|toi) goi lai\b",
      r"\bnhan tin (cho|qua) (anh|chi|toi)\b"],
     "Dạ vâng ạ. Em cảm ơn anh chị, khi nào tiện anh chị gọi lại bên em nhé."),

    # "Ô kê em nhá" sau khi nghe tư vấn: khách xác nhận đã nắm, KHÔNG phải câu
    # hỏi. Kho không có đáp án cho kiểu này nên ở chế độ chỉ chọn trong kho AI
    # đáp "em chưa có thông tin chính xác..." cho một câu chẳng hỏi gì (cuộc
    # d1086216, 08-10-2026). Chỉ nhận họ "ok" đứng MỘT MÌNH; "được", "ừ" có thể
    # là câu trả lời cho câu AI vừa hỏi nên để đường cũ lo.
    ("xac_nhan_ok",
     [r"^\s*(u+ |vang |da )?(ok|oke|okie|okay|o ke|o kay|o key)"
      r"( roi| em| nhe| nha| a| ban| cam on)*\s*$"],
     "Dạ vâng ạ. Anh chị còn cần em hỗ trợ thêm thông tin nào nữa không ạ?"),

    # Lời chào MỞ ĐẦU ("xin chào", "chào em"). Chỉ dùng ở lượt đầu: giữa cuộc
    # gọi thì "chào em" là lời tạm biệt, để kho trả lời (xem `tra_loi_san`).
    # Thiếu luật này, "xin chào" ở lượt đầu rơi xuống kho và bộ chọn ghép nó với
    # câu CHÀO KẾT THÚC "em chào anh chị ạ" - mở lời đã nghe lời tạm biệt.
    ("chao_hoi",
     [r"^\s*(xin )?chao( em| ban| chau| co)?( a| ah)?\s*$", r"^\s*(em|ban|chau) oi\s*$",
      r"^\s*(a\s*lo|alo)\s+(xin )?chao( em| ban)?\s*$"],
     None),

    # Để CUỐI: "alo" trần trụi, sau khi các ý định cụ thể hơn đã xét xong.
    ("chao_bat_may",
     [r"^\s*(a\s*lo\s*)+$", r"^\s*(alo\s*)+$", r"^\s*(nghe|toi nghe|noi di)\s*$",
      r"^\s*(a\s*lo|alo)\s+(em|anh|chi)\s*(oi|a|ah)?\s*$"],
     None),      # tuỳ lúc đầu hay giữa cuộc gọi, xem `tra_loi_san`
]

CHAO_DAU = ("Dạ em chào anh chị ạ. Em là {agent} bên {bank}, em gọi để giới "
            "thiệu chương trình {product} ưu đãi ạ.")
CHAO_LAI = "Dạ em chào anh chị ạ. Em là {agent} bên {bank}, anh chị cần em hỗ trợ gì ạ?"
CHAO_GIUA = "Dạ em vẫn nghe anh chị ạ."


def nhan_dang(text: str) -> str | None:
    """Tên ý định, hoặc None nếu không phải lượt thường gặp."""
    t = _chuan(text)
    if not t:
        return None
    # Quyền điều khiển cuộc gọi phải thắng mọi luật sản phẩm và không chịu trần
    # 8 từ. Danh tính tự động/nguồn số cũng cần trả lời thẳng, kể cả câu ghép.
    dieu_khien = y_dinh_dung_tu_van(text)
    if dieu_khien:
        return dieu_khien
    danh_tinh_nguon = _y_dinh_danh_tinh_nguon(text)
    if danh_tinh_nguon:
        return danh_tinh_nguon
    so_tu = len(t.split())
    # Hai mẫu chắc chắn dưới đây dài hơn một lượt dò hỏi thông thường. Cho riêng
    # chúng tới 12 từ; các ý định khác vẫn giữ trần 8 để không chặn nhầm câu có
    # nội dung thật.
    if so_tu > TOI_DA_TU:
        if so_tu <= 12:
            for ten_dai in ("chua_ro_nhu_cau",):
                ten, mau, _ = next(x for x in BANG if x[0] == ten_dai)
                if any(re.search(m, t) for m in mau):
                    return ten
        return None
    for ten, mau, _ in BANG:
        if ten in (Y_DINH_TU_CHOI, Y_DINH_HEN_LAI, Y_DINH_DANG_BAN):
            # Helper ở trên sở hữu ba ý này để guard phủ định/đổi sản phẩm
            # không bị bảng regex cũ bắt lại.
            continue
        if any(re.search(m, t) for m in mau):
            return ten
    return None


def tra_loi_san(text: str, *, bank: str, agent: str, product: str,
                luot_thu: int = 0) -> tuple[str, str] | None:
    """Trả (ý định, câu trả lời) nếu đây là lượt thường gặp, không thì None."""
    ten = nhan_dang(text)
    if ten is None:
        return None
    if ten == "xac_nhan_ok" and luot_thu <= 1:
        # "Ok" ngay sau lời chào là bảo "em nói đi", chưa có gì để xác nhận.
        ten = "moi_noi_tiep"
    mau = next(c for t, _, c in BANG if t == ten)
    if ten == "chao_hoi":
        # `turn_count` đã tính cả lượt đang xét (add_turn chạy trước), nên lượt
        # đầu của khách là 1 chứ không phải 0.
        if luot_thu > 1:
            return None  # giữa cuộc gọi là lời tạm biệt: để kho trả lời
        mau = CHAO_LAI
    elif mau is None:    # chao_bat_may
        # "A lô" ở LƯỢT ĐẦU của khách = họ chưa nghe được lời chào (nhấc máy
        # chưa kịp áp tai, đường tiếng chưa thông). Đáp "em vẫn nghe" thì cả
        # cuộc khách không biết ai gọi - cuộc 08-10-2026 khách báo "không thấy
        # lời chào luôn". Nên xưng danh lại. `luot_thu` đã tính lượt đang xét
        # (xem `chao_hoi`), trước đây so `== 0` nên nhánh này chưa từng chạy.
        if luot_thu <= 1:
            mau = CHAO_DAU if (product or "").strip() else CHAO_LAI
        else:
            mau = CHAO_GIUA
    return ten, mau.format(bank=bank, agent=agent, product=product)
