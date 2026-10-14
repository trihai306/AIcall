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
Y_DINH_GAN_THU_NHAP_NGUOI_KHAC = "gan_thu_nhap_nguoi_khac"


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
    r"|\b(?:tu van|noi|hoi)\s+tiep(?:\s+di)?\b"
    r"|\b(?:nhung|ma|con|thi)\b.{0,35}\b(?:dong y|san sang)\s+"
    r"(?:nghe\s+(?:gioi thieu|tu van)|nhan\s+(?:thong tin\s+)?quang cao)\b"
    r"|\b(?:gio\s+)?(?:anh|chi|toi|tui|co|chu|bac|minh|chau|em)\s+"
    r"(?:da\s+)?(?:dong y|san sang)\s+(?:nghe\s+(?:gioi thieu|tu van)|"
    r"nhan\s+(?:thong tin\s+)?quang cao)\b")
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
    r"(?<!dung )(?<!khong )(?<!chua )\b(?:"
    r"(?:dung|ngung)\s+(?:cuoc\s+goi|"
    r"goi\s+(?:nua|lai|cho\s+(?:anh|chi|toi|tui|co|chu|bac|em))|"
    r"lien\s+he\s+(?:nua|lai)|trao\s+doi|tu\s+van|noi\s+chuyen)\b"
    r"|(?:dung|thoi)\s+(?:moi|doc|tu van|noi)\b.{0,45}\b(?:nua|tiep)\b"
    r"|(?:dung|thoi)\s+hoi(?:\s+(?:anh|chi|toi|tui|co|chu|bac|em))?\s+"
    r"(?:nua|them)(?:\s+nua)?\b)"
    r"|\bkhong\s+dong\s+y\s+(?:"
    r"(?:tiep\s+tuc\s+)?nghe\s+(?:gioi\s+thieu|tu\s+van|moi\s+chao|quang\s+cao)|"
    r"nhan\s+(?:thong\s+tin\s+)?quang\s+cao)\b"
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

# Khách yêu cầu đổi thu nhập của người khác thành thu nhập của mình. Chỉ bắt
# khi cùng câu có cả thao tác đổi/bỏ chủ thể và đích là chính người gọi; câu
# hỏi giả định chung hoặc xét tổng thu nhập gia đình không khớp mẫu này.
_GAN_THU_NHAP_NGUOI_KHAC = re.compile(
    r"\bbo\s+(?:ten|chu the)\s+(?:cua\s+)?(?:nguoi do|ho|nguoi ay|"
    r"bo|me|ba|vo|chong)\b.{0,45}\b(?:coi|xem)\s+nhu\s+"
    r"(?:anh|chi|toi|tui|minh)\s+(?:kiem|lam|co|nhan)\b"
    r"|\b(?:coi|xem)\s+(?:khoan\s+)?(?:luong|thu nhap)\s+"
    r"(?:do|cua\s+(?:nguoi do|ho|nguoi ay|bo|me|ba|vo|chong))\s+"
    r"(?:la|thanh|nhu)\s+(?:(?:luong|thu nhap)\s+)?(?:cua\s+)?"
    r"(?:anh|chi|toi|tui|minh)\b"
    r"|\b(?:ghi|doi|sua|chuyen)\b.{0,35}\b(?:luong|thu nhap)\b.{0,35}"
    r"\b(?:thanh|sang|la)\s+(?:(?:luong|thu nhap)\s+)?(?:cua\s+)?"
    r"(?:anh|chi|toi|tui|minh)\b")


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
    có hiệu lực. Lệnh dừng rõ ràng hoặc từ chối nghe quảng cáo thắng trạng thái
    bận/hoãn trong cùng lượt, trừ khi chính khách yêu cầu tiếp tục sau đó.
    """
    # "bác già rồi không rành" (không thạo) bỏ dấu là trùng "không rảnh", và
    # AI xin gọi lại một người vừa nhờ nói chậm (bộ thử 12-10-2026). Chỉ phân
    # biệt được khi lời khách còn dấu, nên đổi chữ TRƯỚC khi bỏ dấu.
    text = re.sub(r"\brành\b", "thạo", unicodedata.normalize("NFC", text or ""),
                  flags=re.IGNORECASE)
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

    # Dừng rõ ràng là ứng viên mức 4. Nó phải thắng một mô tả bận/lái xe hoặc
    # lời hẹn xuất hiện sau, nếu không hệ thống lại hỏi giờ gọi lại sau khi
    # khách vừa yêu cầu kết thúc. Một yêu cầu tiếp tục trực tiếp ở phía sau vẫn
    # là lần đổi ý mới nhất và hủy lệnh dừng trước đó.
    dung_ro = [x for x in ung_vien if x[1] == 4]
    if dung_ro:
        dung_cuoi = max(dung_ro, key=lambda x: x[0])
        tiep_tuc_sau_dung = [x for x in tiep_tuc if x >= dung_cuoi[4]]
        if not tiep_tuc_sau_dung:
            cuoi = dung_cuoi
        else:
            tiep_tuc_cuoi = max(tiep_tuc_sau_dung)
            sau_tiep_tuc = [x for x in ung_vien if x[0] > tiep_tuc_cuoi]
            if not sau_tiep_tuc:
                return None
            cuoi = max(sau_tiep_tuc, key=lambda x: (x[0], x[1]))
    else:
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
    r"|\b(?:em|ban|chau)\s+la\s+tro ly tu dong\b"
    r"|\b(?:ai|robot|may)\s+hay\s+(?:nguoi|nguoi that|nhan vien)\b"
    r"|\b(?:nguoi|nguoi that)\s+hay\s+(?:ai|robot|may)\b"
    r"|\b(?:dang noi(?: chuyen)?|noi chuyen)\s+voi\s+(?:robot|may|nguoi that)\b"
    r"|\bco phai\s+(?:la\s+)?(?:robot|may)(?:\s+goi)?\b"
    r"|\b(?:robot|may)\s+phai khong\b")
_HOI_NGUON_SO = re.compile(
    r"\b(?:sao|tai sao)\s+(?:em|minh|ben em|ban|chau)?\s*(?:lai\s+)?co\s+"
    r"(?:sdt|so dien thoai|so\s+(?:cua\s+)?(?:anh|chi|toi|tui|bac|co|chu|minh|em))\b"
    r"|\b(?:sdt|so dien thoai|so\s+(?:cua\s+)?"
    r"(?:anh|chi|toi|tui|bac|co|chu|minh|em|nay))\b.{0,30}\b"
    r"(?:o dau ra|lay dau|tu dau|tu nguon nao|nguon nao|bang cach nao)\b"
    r"|\b(?:lay|co)\s+(?:sdt|so dien thoai|so\s+(?:cua\s+)?"
    r"(?:anh|chi|toi|tui|bac|co|chu|minh|em))\b.{0,25}\b"
    r"(?:o dau|tu dau|tu nguon nao|nguon nao)\b"
    r"|\bai\s+(?:cho|dua)\b.{0,18}\b(?:sdt|so dien thoai|so(?:\s+(?:cua\s+)?"
    r"(?:anh|chi|toi|tui|bac|co|chu|minh|em))?)\b"
    r"|\bnguon\s+(?:cua\s+)?(?:sdt|so dien thoai|so)\b"
    r"|\bsao\s+(?:em|minh|ben em|ban|chau)?\s*(?:lai\s+)?biet\s+"
    r"(?:sdt|so dien thoai|so\s+(?:cua\s+)?(?:anh|chi|toi|tui|bac|co|chu|minh|em))\b")


def _y_dinh_danh_tinh_nguon(text: str) -> str | None:
    t = _chuan(text)
    hoi_ai = bool(_HOI_AI.search(t))
    # Sau khi bỏ dấu và hạ chữ, "em là AI" và câu hỏi tên người "em là ai"
    # giống hệt nhau. Chỉ coi dạng khẳng định ngắn là danh tính tự động khi
    # đầu vào thật sự có acronym ``AI`` viết hoa; "em là ai" vẫn để ``ai_day``.
    if not hoi_ai and re.search(r"\bAI\b", text or ""):
        hoi_ai = bool(re.search(
            r"\b(?:em|ban|chau)\s+(?:co phai\s+)?(?:la\s+)?ai\b"
            r"|\bai\s+(?:hay|phai khong)\b"
            r"|\b(?:nguoi|nguoi that|nhan vien)\s+hay\s+ai\b",
            t,
        ))
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
    (Y_DINH_GAN_THU_NHAP_NGUOI_KHAC, [],
     "Dạ em cần ghi đúng người có thu nhập. Anh chị cho em xin mức thu nhập "
     "thực tế của mình; nếu muốn xét thu nhập chung gia đình, anh chị nói rõ "
     "từng nguồn để em kiểm tra ạ?"),

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

    # "chị đang bận em nói nhanh nhé": khách CHO PHÉP nói, chỉ cần ngắn. Luật
    # `dang_ban` từng xin gọi lại (đóng vai 14-10-2026). Phải đứng TRƯỚC `dang_ban`.
    ("noi_nhanh",
     [r"\bnoi (nhanh|ngan|gon|ngan gon|le)\b(?!.{0,12}\b(qua|khong nghe|khong kip|lam)\b)"],
     "Dạ vâng, em nói ngắn gọn thôi ạ. Anh chị quan tâm phần nào thì cứ hỏi em ạ."),

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
    # Khách xin gửi tài liệu qua Zalo/tin nhắn, hoặc đòi làm hồ sơ ngay trong cuộc
    # gọi: AI không gửi được gì và không làm hồ sơ được. Bộ thử 12-10-2026: mô
    # hình tự viết khi thì "chưa cung cấp Zalo", khi thì bảo khách tự gọi lại.
    # "thế máy thì biết gì mà tư vấn": khách coi thường vì là máy. Nói thật mình
    # là trợ lý tự động và tư vấn theo thông tin ngân hàng công bố. Để mô hình tự
    # viết thì có lần nó nhận mình là nhân viên thật (bộ thử 12-10-2026).
    ("may_biet_gi",
     [r"\b(may|robot|ai|tong dai tu dong)\b.{0,14}\b(biet gi|thi biet|ma (cung )?tu van|tu van (cai )?gi)\b"],
     "Dạ em là trợ lý tự động của ngân hàng ạ. Em tư vấn theo đúng thông tin sản phẩm ngân "
     "hàng công bố, phần nào cần chuyên viên thì em xin ghi nhận để chuyên viên liên hệ anh chị ạ."),

    # "ừ để mai cô ra": khách tự hẹn RA QUẦY. Kho từng đáp "em xin ghi nhận để bên
    # em liên hệ lại anh chị vào ngày mai" - ngược ý khách (khách đóng vai 12-10-2026).
    # "lại ngân hàng à dạo này gọi suốt": khách phàn nàn bị gọi nhiều. Kho từng
    # đáp "em xin lỗi vì anh chị không nhận ra số" rồi hỏi luôn số tiền vay.
    ("bi_goi_nhieu",
     [r"\bgoi (suot|hoai|mai|lien tuc|nhieu the|nhieu vay|nhieu qua|lam the|suot ngay)\b",
      r"\b(lai|toan) (ngan hang|tiep thi|moi vay)\b.{0,20}\b(a|ha|nua)\b"],
     "Dạ em xin lỗi vì đã làm phiền anh chị ạ. Em xin phép nói nhanh một phút thôi, "
     "anh chị thấy không phù hợp thì em dừng ngay ạ."),

    ("hen_ra_quay",
     [r"\b(mai|mot|hom nao|hom sau|tuan sau|cuoi tuan|chieu nay|sang mai|luc nao ranh|khi nao ranh|de)\b"
      r".{0,24}\b(ra|den|qua|ghe|chay ra|tat qua)\b( (quay|chi nhanh|ngan hang|phong giao dich|do|ben do|ben em))?"
      r"( (nhe|nha|a|em|vay|xem|hoi|lam))*\s*$"],
     "Dạ vâng ạ, em cảm ơn anh chị. Khi ra quầy anh chị mang theo giấy tờ tuỳ thân để được "
     "hỗ trợ ạ."),

    # "ok em ghi lại đi": khách ĐỒNG Ý để ghi nhận. Kho từng đáp "em chờ máy, khi
    # nào anh chị sẵn sàng thì báo em" rồi hỏi lại đúng câu khách vừa gật.
    ("dong_y_ghi_nhan",
     # Neo cả câu: "ghi lại lãi suất cho anh", "anh ghi lại số em đi" là việc khác.
     [r"^\s*((ok|oke|u+|uh|duoc|vang|da|the|vay|thoi|roi)\s+)*(thi\s+)?(em\s+)?"
      r"(ghi (lai|nhan)|dang ky|len ho so|lam ho so)"
      r"(\s+(di|giup|cho|luon|nhe|nha|ho|anh|chi|em|toi|minh|a))*\s*$"],
     "Dạ vâng ạ, em đã ghi nhận nhu cầu của anh chị. Chuyên viên của ngân hàng sẽ liên hệ lại "
     "để hướng dẫn hồ sơ ạ. Em cảm ơn anh chị ạ."),

    ("xin_gui_qua_kenh",
     [r"\b(gui|nhan|ban)\b.{0,25}\b(zalo|sms|email|mail|link|facebook|messenger)\b",
      r"\b(zalo|email|mail)\b.{0,15}\b(cho|qua) (anh|chi|toi|minh)\b"],
     "Dạ qua cuộc gọi này em chưa gửi được tài liệu cho anh chị ạ. Em xin ghi nhận "
     "để chuyên viên liên hệ và hướng dẫn cụ thể cho anh chị ạ."),

    ("lam_qua_dien_thoai",
     [r"\b(lam|dang ky|mo|nop ho so|lam ho so|lam thu tuc)\b.{0,20}"
      r"\b(qua dien thoai|qua cuoc goi nay|tren dien thoai)\b.{0,12}\b(duoc khong|duoc ko|khong)\b"],
     "Dạ qua cuộc gọi này em mới tư vấn thông tin thôi ạ. Em xin ghi nhận để chuyên "
     "viên liên hệ hướng dẫn anh chị làm hồ sơ ạ."),

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
     [r"^\s*((da|vang|u|o)\s+)?(a\s*lo\s*)+(a)?\s*$", r"^\s*(alo\s*)+$", r"^\s*(nghe|toi nghe|noi di)\s*$",
      # "chú nghe", "alo cô nghe đây": người lớn tuổi nhấc máy hay nói vậy.
      r"^\s*(a\s*lo\s+|alo\s+)?(anh|chi|co|chu|bac|ong|ba|toi|tui|em|chau)\s+nghe(\s+(day|a|em|chau))*\s*$",
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
    # Đang lái xe / đang họp thì vẫn xin gọi lại: nói tiếp lúc đó là không an toàn.
    if dieu_khien == "dang_ban" and len(t.split()) <= 10 and not re.search(
            r"\b(lai xe|dang hop|chay xe|di duong)\b", t) and any(
            re.search(m, t) for m in next(x for x in BANG if x[0] == "noi_nhanh")[1]):
        return "noi_nhanh"          # "đang bận, em nói nhanh nhé": được nói, chỉ cần ngắn
    if dieu_khien:
        return dieu_khien
    danh_tinh_nguon = _y_dinh_danh_tinh_nguon(text)
    if danh_tinh_nguon:
        return danh_tinh_nguon
    if _GAN_THU_NHAP_NGUOI_KHAC.search(t):
        return Y_DINH_GAN_THU_NHAP_NGUOI_KHAC
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
            # "chờ anh tí con ơi đừng nghịch ừ em nói đi": lời với người khác chen
            # vào làm câu dài quá trần, nhưng vế CUỐI vẫn là mời nói tiếp.
            if re.search(r"\b(em|chau|ban) noi (di|tiep|tiep di)\s*$", t):
                return "moi_noi_tiep"
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
