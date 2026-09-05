import logging
import re

import httpx

from backend.config import settings
from backend.core.logging_config import Timer
from backend.services.audio_utils import pcm_to_wav

logger = logging.getLogger(__name__)

# Whisper BỊA CHỮ khi đầu vào chỉ có nhiễu - nó sinh ra câu tiếng Việt trôi chảy
# từ tạp âm. Trên đường thoại EDGE điều này xảy ra liên tục: một cuộc gọi thật
# cho ra "điều này đã khiến nhiều người mơ ước được hiểu rõ" lặp y hệt qua bốn
# lượt, còn AI thì trả lời rỗng. Ba dấu hiệu dưới đây lọc được phần lớn.

# `no_speech_prob` LUÔN BẰNG 0 trên PhoWhisper - đo trên 6 mẫu (nhiễu lẫn giọng)
# đều ra 0.000, nên nó vô dụng ở đây. Giữ lại phép kiểm phòng khi đổi mô hình,
# nhưng đừng trông vào nó.
NGUONG_KHONG_TIENG = 0.6

# `avg_logprob` thì tách rất sạch. Đo được (scripts/kiem_loc_stt.py):
#     giọng sạch        -0.015      giọng + nhiễu -30dB   -0.007
#     nhiễu -22 dBFS    -0.925      nhiễu -28 dBFS        -0.643
#     nhiễu -35 dBFS    -0.823      nhiễu -45 dBFS        -0.242
# Chọn -0.30: cách giọng thật một quãng rất rộng nên không cắt nhầm lượt của
# khách, mà vẫn bắt được mọi mức nhiễu đủ to để vượt ngưỡng VAD. Riêng nhiễu
# -45 dBFS lọt qua đây, nhưng nó quá nhỏ để mở được một lượt (RMS ~180 so với
# ngưỡng VAD 700), nên VAD chặn trước.
NGUONG_TU_TIN = -0.30
# Ngưỡng NỚI cho lượt ngắn (<=0.7s và <=5 chữ). Xem `_nguong_tu_tin` để biết vì
# sao phải nới và vì sao nới vẫn an toàn.
NGUONG_TU_TIN_NGAN = -0.55
# Ngắn hơn thế thì không đủ làm một lượt nói - thường là mảnh vụn kiểu "n.".
DAI_TOI_THIEU = 2

# --- Lưới chặn cho VÙNG MỜ của lượt ngắn ---------------------------------
#
# Ngưỡng nới -0.55 sinh ra một lỗ: khi khách gọi từ chỗ CÓ TẠP ÂM NGOÀI,
# Whisper nặn ra cụm ngắn đúng ngữ pháp nhưng vô nghĩa, và chúng lọt. Đo trên
# cuộc gọi thật `31535879` (nền kênh 18.3 so với 7-8 ở các cuộc yên tĩnh):
#
#     -0.038  'a lô'                  <- THẬT
#     -0.249  'có rõ ràng'            <- THẬT
#     -0.447  'vâng'                  <- THẬT
#     -0.471  'đủ lợi đủ thời điểm'   <- RÁC, lọt
#     -0.474  'bạn có thêm'           <- RÁC, lọt
#
# Siết ngưỡng KHÔNG giải quyết được: chữ thật tệ nhất (-0.447) và rác tốt nhất
# (-0.471) chỉ cách nhau 0.024 - trong khoảng nhiễu đo. Siết quá tay là quay
# lại đúng lỗi "khách nói xong AI im".
#
# Cách tách chắc hơn: câu đáp NGẮN có thật trong hội thoại bán hàng là một tập
# ĐÓNG và nhỏ. Trong vùng mờ thì đòi bản phiên âm phải NẰM TRỌN trong tập đó.
# Chỉ áp cho vùng mờ, nên câu ngắn mà mô hình TIN (trên -0.30) vẫn đi thẳng -
# khách hỏi câu ngắn lạ vẫn không bị chặn.
# Danh sách phải phủ ĐỦ từ vựng khách thật dùng, không chỉ tiếng đáp trống. Bản
# đầu chỉ có "alo/vâng/ừ/ok" và vứt luôn "thôi không cần", "gọi lại sau",
# "lãi bao nhiêu" - tức là vứt đúng những câu QUYẾT ĐỊNH kết quả cuộc gọi, đổi
# một lỗi khó chịu lấy một lỗi tệ hơn.
#
# Vẫn chặn được rác vì phép so đòi TOÀN BỘ chuỗi khớp: "đủ lợi đủ thời điểm" có
# "thoi" trong danh sách nhưng "du"/"loi"/"diem" thì không, "bạn có thêm" có
# "co" nhưng "ban"/"them" thì không. Thêm từ vào đây phải là từ khách THẬT nói
# trong câu ngắn - đừng thêm từ chỉ vì thấy nó trong một bản phiên âm rác.
_DAP_NGAN = (
    # tiếng đáp trống
    r"a ?lo|alo|vang|u+|o ?kay|ok|duoc|khong|ko|co|roi|dung|the|vay|a|da|u ?hu"
    r"|nghe|nua|gi|sao|hi|hello|xin|chao|cam on|thoi|het"
    # đại từ
    r"|toi|anh|em|chi|minh|ban|ai|day|do|nay|nao|ma|la|thi|voi|cho|de"
    r"|di|nhe|nha|ha|hen|dau|day a|nhi"
    # nghiệp vụ: hỏi giá / điều kiện
    r"|lai|suat|bao|nhieu|tien|trieu|tram|ty|phi|thang|nam|han|muc|may"
    r"|vay|no|goi|lai|sau|luc|khi|gio"
    # nghiệp vụ: từ chối / hẹn / yêu cầu nhắc lại
    r"|ban|ron|can|quan tam|noi|hieu|biet|ro|lam|gap|xong|dang|se|dinh"
    r"|hon|tinh|xem|nghi|thu|thay|muon|chua"
    r"|ho so|giay to|thu tuc|dieu kien"
)
_DAP_NGAN_RE = re.compile(rf"^\s*(({_DAP_NGAN})[\s,.!?]*)+$")

# Những câu Whisper hay bịa trên nền im lặng hoặc nhiễu.
#
# CẨN THẬN: danh sách này có "xin chào", "cảm ơn", "hết rồi" - đều là câu KHÁCH
# NÓI THẬT, liên tục, trong mọi cuộc gọi. Trước đây khớp mẫu là vứt cả lượt,
# nên khách chào hay cảm ơn là màn hình trống trơn, không báo gì. Lỗi này có ở
# CẢ đường web lẫn đường thoại vì lọc nằm ở phần dùng chung.
# Xem scripts/kiem_loc_cau_ngan.py.
_RAC = re.compile(
    r"^(hãy subscribe|subscribe|cảm ơn( các bạn)?( đã xem)?|ghiền mì gõ"
    r"|hết rồi|xin chào|\.|…|\s)*$", re.IGNORECASE)

# Nên KHÔNG vứt theo câu chữ đơn thuần, mà đòi thêm độ tin thấp. Hai vùng tách
# rất rộng (giọng thật -0.02, nhiễu -0.24 trở xuống) nên -0.15 nằm gọn ở giữa:
# khách chào thật thì giữ, Whisper bịa trên nhiễu thì vẫn chặn được.
NGUONG_TU_TIN_RAC = -0.15

# Token nội bộ của mô hình lọt ra bản phiên âm. Bắt được trên cuộc gọi thật:
# PhoWhisper trả "unk thông tin căn cước." khi đoạn đầu không giải mã được, và
# chữ "unk" đó đi thẳng vào prompt của LLM như thể khách đã nói ra.
# Dạng thẻ `<|...|>` cũng gom luôn: khi máy chủ không lọc, chúng lọt nguyên văn.
# "unk" đứng riêng KHÔNG phải từ tiếng Việt nào nên xoá an toàn; chỉ xoá khi nó
# là một từ trọn vẹn, không đụng tới từ chứa nó.
_TOKEN_RAC = re.compile(r"<\|[^|>]*\|>|</?unk>|\bunk\b", re.IGNORECASE)


def _don_token(text: str) -> str:
    """Bỏ token nội bộ của mô hình, gộp khoảng trắng thừa."""
    return re.sub(r"\s{2,}", " ", _TOKEN_RAC.sub(" ", text)).strip(" .,")


# Mồi từ vựng cho Whisper. Viết thành CÂU VĂN TỰ NHIÊN chứ không phải danh sách
# từ - bộ giải mã nghiêng theo phân bố văn bản, nên một đoạn văn cùng lĩnh vực
# dẫn dắt tốt hơn hẳn một chuỗi từ rời rạc.
#
# Cần vì kênh thoại 8kHz cắt mất phần lớn phụ âm: đo trên cuộc gọi thật,
# "lãi suất" bị nghe thành "lãnh xuất" - đúng từ khoá quan trọng nhất của kịch
# bản bán hàng, và LLM không thể đoán đúng ý từ một chuỗi đã sai như vậy.
MOI_TU_VUNG = (
    "Cuộc gọi tư vấn ngân hàng. Khách hỏi về lãi suất, hạn mức vay, "
    "vay tín chấp, vay mua nhà, thẻ tín dụng, sổ tiết kiệm. "
    "Hồ sơ gồm căn cước công dân, sao kê lương, hợp đồng lao động. "
    "Ngân hàng giải ngân trong hai mươi bốn giờ, thời hạn trả góp, "
    "phí thường niên, tất toán trước hạn. "
    # Kèm dãy số: khách đọc số tiền, số điện thoại, số căn cước liên tục, mà
    # kênh 8kHz làm mất thanh điệu nên số hay bị nghe lệch dấu.
    "Số điện thoại không ba chín sáu một hai ba bốn năm sáu bảy tám chín."
)

# Mồi thêm theo VÙNG MIỀN (Điều 6: "Có thể nhận diện giọng vùng miền").
#
# Nối THÊM vào MOI_TU_VUNG chứ không thay thế: phần từ vựng ngân hàng ở trên đã
# được đo là có lợi, bỏ nó đi để lấy phần vùng miền là đánh đổi mù.
#
# PhoWhisper vốn huấn luyện trên tiếng Việt nhiều vùng nên đây KHÔNG phải cách
# "dạy" nó một giọng mới — nó chỉ nghiêng bộ giải mã về phía chính tả chuẩn của
# các cặp âm mà vùng đó phát âm không phân biệt. Muốn biết có ăn thua không thì
# phải ĐO: chạy scripts/do_vung_mien.py trên mẫu thu thật.
MOI_VUNG_MIEN = {
    "bac": (
        " Giọng miền Bắc. Phân biệt l và n, tr và ch, s và x, r và d: "
        "lãi suất, nợ, trả góp, chuyển khoản, sổ tiết kiệm, xin chào, rất tốt."
    ),
    "trung": (
        " Giọng miền Trung. Thanh điệu nặng, hỏi và ngã gần nhau: "
        "lãi suất, hạn mức, hồ sơ, giải ngân, tất toán, mở thẻ."
    ),
    "nam": (
        " Giọng miền Nam. Không phân biệt v và d và gi, n và ng cuối, "
        "t và c cuối, hỏi và ngã: vay vốn, giải ngân, hạn mức, tất toán, "
        "sổ tiết kiệm, thẻ tín dụng."
    ),
}


def moi_tu_vung(vung: str = "") -> str:
    """Câu mồi cho Whisper, kèm phần vùng miền nếu có cấu hình."""
    return MOI_TU_VUNG + MOI_VUNG_MIEN.get((vung or "").strip().lower(), "")


# Sửa những chuỗi nghe nhầm ĐÃ QUAN SÁT ĐƯỢC trên cuộc gọi thật. Cố ý giữ HẸP:
# chỉ sửa đúng cụm đã thấy, KHÔNG dò gần đúng toàn bộ câu. Dò gần đúng thì sớm
# muộn cũng sửa nhầm một câu vốn đúng, mà lỗi đó khó phát hiện hơn nhiều.
_SUA_NGHE_NHAM = [
    (re.compile(r"\blãnh\s+xuất\b", re.I), "lãi suất"),
    (re.compile(r"\blãi\s+xuất\b", re.I), "lãi suất"),
    (re.compile(r"\blải\s+suất\b", re.I), "lãi suất"),
    (re.compile(r"\blại\s+suất\b", re.I), "lãi suất"),
    (re.compile(r"\bcẩn\s+cước\b", re.I), "căn cước"),
    (re.compile(r"\bcăng\s+cước\b", re.I), "căn cước"),
    (re.compile(r"\btính\s+chấp\b", re.I), "tín chấp"),
    # "tính chất" LÀ TỪ THẬT trong tiếng Việt, nên chỉ sửa khi đứng sau "vay" -
    # "vay tính chất" thì chắc chắn là "vay tín chấp", còn "tính chất của khoản
    # vay" phải để nguyên. Đây là ranh giới giữa sửa đúng và sửa hỏng.
    (re.compile(r"\bvay\s+tính\s+chất\b", re.I), "vay tín chấp"),
    (re.compile(r"\bhạng\s+mức\b", re.I), "hạn mức"),
    # --- "hạn mức" nghe nhầm, quan sát trên tiếng khách THẬT (05-09-2026) ---
    #
    # Đo bằng `scripts/do_xu_ly_tieng_khach.py` trên 7 lượt của cuộc gọi
    # 4cd44fb7 (đã qua GSM/AMR thật): cùng từ "hạn mức" hỏng theo cùng một kiểu
    # ở 7/7 cách xử lý âm thanh - lọc nhiễu, cổng phổ, chuẩn hoá mức đều không
    # cứu được, mà lọc còn làm CER tệ gấp 2,1 lần. Tiếng không mang đủ thông
    # tin chứ không phải nhiễu che mất, nên chữa ở tầng CHỮ mới đúng chỗ.
    #
    # "lợn sơn" / "lớn sơn" không phải cụm tiếng Việt có thật nên sửa thẳng.
    # Hai chữ đứng RIÊNG thì không đụng tới ("giá thịt lợn", "nghề sơn nhà").
    (re.compile(r"\bl[ợớ]n\s+sơn\b", re.I), "hạn mức"),
    # "hắn mừng" LÀ cụm có thật ("hắn mừng lắm"), nên chỉ sửa khi theo sau là
    # "được" - đúng dạng đã quan sát ("hắn mừng được bao nhiêu"). Khách gọi
    # ngân hàng gần như không bao giờ nói "hắn mừng được...".
    (re.compile(r"\bhắn\s+mừng(?=\s+được\b)", re.I), "hạn mức"),
    # "có sẵn mức" LÀ cách nói có thật trong bán hàng ("có sẵn mức giá tốt"),
    # nên chặn đúng trường hợp đó bằng lookbehind.
    (re.compile(r"(?<!có )\bsẵn\s+mức\b", re.I), "hạn mức"),
]


def _sua_nghe_nham(text: str) -> str:
    for mau, dung in _SUA_NGHE_NHAM:
        text = mau.sub(dung, text)
    return _sua_day_so(text)


# --- Sửa số nghe nhầm theo NGỮ CẢNH DÃY SỐ --------------------------------
# Kênh thoại 8kHz làm mất thanh điệu trước tiên, nên số bị nghe lệch dấu: đo trên
# cuộc gọi thật, "một hai ba bốn năm sáu bảy tám" ra "...năm sau vẩy tắm".
# Trong bán hàng ngân hàng khách đọc số liên tục (số tiền, số điện thoại, căn
# cước) nên đây không phải lỗi vặt.
#
# CHỈ SỬA KHI TỪ NẰM TRONG MỘT DÃY SỐ. "sau" đứng một mình là từ bình thường
# ("gọi lại sau nhé"), nhưng đứng giữa "năm ... bảy" thì chắc chắn là "sáu".
# Nhờ ràng buộc này mà không đụng tới "sau", "năm", "tư" dùng nghĩa thường.
_TU_SO_VI = ["không", "một", "mốt", "hai", "ba", "bốn", "tư", "năm", "lăm",
             "sáu", "bảy", "tám", "chín", "mười"]
_TU_SO_SET = set(_TU_SO_VI)


def _bo_dau(s: str) -> str:
    """Bỏ dấu tiếng Việt. PHẢI thay `đ` riêng.

    `đ` là U+0111, một ký tự độc lập KHÔNG có phân rã chuẩn, nên `NFD` để nguyên
    và nó sống sót qua bộ lọc `Mn`. Thiếu dòng thay này thì "được" ra "đuoc",
    "đang" ra "đang" - mọi phép so trên bản bỏ dấu đều trượt ở đúng những từ có
    đ. Bắt được khi lưới `_DAP_NGAN_RE` vứt oan "vay được không" và "anh đang
    bận". Bản khác trong `luot_thuong_gap.bo_dau` vốn đã làm đúng.
    """
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower())
                if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d")


_SO_KHONG_DAU: dict[str, str] = {}
for _t in _TU_SO_VI:
    _SO_KHONG_DAU.setdefault(_bo_dau(_t), _t)


def _so_gan_nhat(tu: str) -> str | None:
    """Từ số gần nhất nếu đủ giống. So trên bản BỎ DẤU vì thanh điệu mất trước."""
    kd = _bo_dau(tu)
    if kd in _SO_KHONG_DAU:
        return _SO_KHONG_DAU[kd]
    for goc_kd, goc in _SO_KHONG_DAU.items():
        if len(goc_kd) == len(kd) and sum(a != b for a, b in zip(goc_kd, kd)) == 1:
            return goc
    return None


def _sua_day_so(text: str, toi_thieu: int = 3) -> str:
    """Sửa từ nghe nhầm nằm TRONG dãy số từ `toi_thieu` phần tử trở lên."""
    tu = text.split()
    if len(tu) < toi_thieu:
        return text
    sach = [t.strip(".,!?").lower() for t in tu]
    la_so = [t in _TU_SO_SET for t in sach]
    gan = [_so_gan_nhat(t) for t in sach]

    i = 0
    while i < len(tu):
        if not la_so[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(tu) and (la_so[j + 1] or gan[j + 1]):
            j += 1
        n = j - i + 1
        # đòi ĐA SỐ là số thật, để một từ giống số không tự kéo cả câu thành dãy
        if n >= toi_thieu and sum(la_so[i:j + 1]) >= (n + 1) // 2:
            for k in range(i, j + 1):
                if not la_so[k] and gan[k]:
                    tu[k] = gan[k]
        i = j + 1
    return " ".join(tu)


class STTService:
    """Whisper.cpp HTTP server client for speech-to-text."""

    def __init__(self):
        self.base_url = settings.whisper_server_url
        # Cùng lý do như llm_service: keepalive mặc định 5s khiến mỗi lượt nói
        # cách nhau lâu phải bắt tay TCP lại, cộng thêm độ trễ vào STT.
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=600.0),
        )

    @staticmethod
    @staticmethod
    def _lap_khong_the_that(text: str) -> str:
        """Whisper kẹt vòng lặp trên tiếng nhiễu - trả lý do, rỗng nếu bình thường.

        Bắt được trong cuộc gọi thật (2026-08-05):
            "mua nhà máy bay mua bay mua bay mua bay mua bay mua bay mua bay..."

        Đây là kiểu hỏng riêng của bộ giải mã tự hồi quy: nó rơi vào chu trình và
        sinh mãi một cụm. `avg_logprob` KHÔNG bắt được vì trong vòng lặp mô hình
        rất "tự tin" - câu càng lặp thì điểm càng đẹp, đúng ngược với thứ ta cần.

        Đo theo TỈ LỆ TỪ LẶP LẠI chứ đừng cấm từ trùng: tiếng Việt lặp từ là bình
        thường ("dạ dạ", "vâng vâng", "alo alo", "không không"). Chỉ khi một cụm
        chiếm gần hết câu DÀI thì mới là vòng lặp máy.
        """
        tu = text.lower().split()
        if len(tu) < 8:            # câu ngắn lặp là bình thường
            return ""
        # Cụm 2 từ nào chiếm quá nửa số cụm -> vòng lặp.
        cum = [" ".join(tu[i:i + 2]) for i in range(len(tu) - 1)]
        if not cum:
            return ""
        hay_nhat = max(set(cum), key=cum.count)
        ti_le = cum.count(hay_nhat) / len(cum)
        if ti_le >= 0.5:
            return f"kẹt vòng lặp: {hay_nhat!r} chiếm {ti_le:.0%} câu"
        # Hoặc: rất ít từ khác nhau trong một câu dài.
        if len(set(tu)) <= len(tu) // 4:
            return f"kẹt vòng lặp: chỉ {len(set(tu))} từ khác nhau trong {len(tu)} từ"
        return ""

    @staticmethod
    def _nguong_tu_tin(text: str, giay: float) -> float:
        """Ngưỡng `avg_logprob`, NỚI RA cho lượt ngắn.

        VÌ SAO: lượt càng ngắn thì `avg_logprob` càng xấu dù nghe rõ y hệt - đó
        là bản chất phép tính (ít token nên mỗi token nặng hơn trong trung bình),
        không phải dấu hiệu nghe kém. Ngưỡng cố định vì thế vứt oan đúng những
        câu đáp NGẮN quan trọng nhất khi bán hàng: "alo", "vâng", "được".

        Đo trên cuộc gọi thật, cắt theo đúng logic VAD (scripts/soi_tung_luot.py):
            460ms -> -0.14      660ms -> -0.05      1800ms -> -0.11
            380ms -> -0.32  BỊ VỨT, mà nội dung "a lô a lô" hoàn toàn ĐÚNG
        Người dùng báo đúng triệu chứng đó: nói "alo" mà máy im.

        VÌ SAO NỚI VẪN AN TOÀN: Whisper bịa chữ trên nhiễu thì sinh ra câu DÀI và
        trôi chảy, không phải hai ba tiếng cụt. Nhiễu đo được cho avg_logprob
        -0.64 tới -0.93, vẫn nằm dưới mức nới -0.55.

        XÉT THEO SỐ CHỮ, KHÔNG THEO THỜI GIAN. Bản đầu xét cả thời gian và đã
        SAI: đoạn đưa vào STT gồm cả quãng im cuối lượt (750ms), nên lượt nói
        380ms đo ra 1.3 giây và điều kiện thời gian không bao giờ đúng. Số chữ
        mới là thứ phản ánh đúng "câu ngắn", và cũng chính là chỗ tựa của lập
        luận an toàn ở trên.
        """
        if len(text.split()) <= 5:
            return NGUONG_TU_TIN_NGAN
        return NGUONG_TU_TIN

    def _dang_ngo(self, text: str, khong_tieng: float, tu_tin: float,
                  giay: float = 0.0) -> str:
        """Trả lý do nếu bản phiên âm đáng ngờ, chuỗi rỗng nếu tin được."""
        if len(text) < DAI_TOI_THIEU:
            return f"quá ngắn ({len(text)} ký tự)"
        # Câu hay bị bịa: chỉ vứt khi độ tin CŨNG thấp. Khách chào thật thì
        # avg_logprob quanh -0.02, Whisper bịa trên nhiễu thì từ -0.24 trở xuống.
        if _RAC.match(text) and tu_tin <= NGUONG_TU_TIN_RAC:
            return f"câu hay bị bịa + avg_logprob {tu_tin:.2f}"
        if khong_tieng >= NGUONG_KHONG_TIENG:
            return f"no_speech_prob {khong_tieng:.2f}"
        if (lap := self._lap_khong_the_that(text)):
            return lap
        nguong = self._nguong_tu_tin(text, giay)
        if tu_tin <= nguong:
            return f"avg_logprob {tu_tin:.2f} <= {nguong}"
        # VÙNG MỜ của lượt ngắn: đã qua ngưỡng nới nhưng chưa đạt ngưỡng thường.
        # Ở đây mới đòi thêm rằng nó phải GIỐNG một câu đáp ngắn có thật -
        # xem `_DAP_NGAN_RE` để biết vì sao không siết ngưỡng được.
        if nguong < tu_tin <= NGUONG_TU_TIN and not _DAP_NGAN_RE.match(_bo_dau(text)):
            return f"cụm ngắn lạ + avg_logprob {tu_tin:.2f}"
        return ""

    # ĐÃ BỎ luật "lặp nguyên văn lượt trước". Nghe thì hợp lý - mô hình bịa trên
    # cùng loại nhiễu cho ra đúng một câu, lặp qua nhiều lượt - nhưng nó vứt
    # nhầm cả lượt THẬT: `pipeline.speculate()` phiên âm phần câu đang nói, rồi
    # lượt thật phiên âm lại toàn bộ; hai bản trùng nhau là chuyện bình thường,
    # và luật đó vứt mất bản thứ hai. Đã bắt được khi phép đo bộ lọc nhiễu cho
    # CER 0.86 một cách vô lý: hai lần gọi liên tiếp trên cùng câu, lần sau bị
    # chặn. `avg_logprob` vốn đã tách sạch nhiễu khỏi giọng thật nên không cần.

    async def moc_tung_chu(self, wav: bytes) -> list[dict]:
        """Phiên âm KÈM mốc thời gian từng chữ. Trả danh sách đoạn có khoá `words`.

        Chỉ dùng cho đường XUẤT FILE: bật mốc chữ buộc faster-whisper chạy thêm
        một lượt căn chữ nên chậm hơn hẳn, mà đường thoại thì có trần TTFA.
        Chỗ dùng: cắt mẩu bù đuôi (xem `backend/services/bu_duoi.py`).

        KHÔNG mồi từ vựng: mồi kéo bộ giải mã về phía văn bản ngân hàng, mà mẩu
        bù ("Tạm biệt") nằm ngoài miền đó - mồi vào là dễ nghe chệch đúng chữ ta
        cần tìm.
        """
        response = await self.client.post(
            f"{self.base_url}/inference",
            files={"file": ("audio.wav", wav, "audio/wav")},
            data={
                "language": "vi",
                "response_format": "verbose_json",
                "temperature": "0",
                "word_timestamps": "1",
            },
        )
        response.raise_for_status()
        return response.json().get("segments") or []

    async def _goi_whisper(self, wav: bytes, moi: str) -> tuple[str, float, float] | None:
        """Một lần gọi máy chủ. Trả (chữ, no_speech, logprob) hoặc None nếu lỗi."""
        response = await self.client.post(
            f"{self.base_url}/inference",
            files={"file": ("audio.wav", wav, "audio/wav")},
            data={
                "language": "vi",
                "response_format": "verbose_json",
                "temperature": "0",
                "prompt": moi,
            },
        )
        if response.status_code != 200:
            logger.error(f"Whisper server error: {response.status_code} {response.text}")
            return None

        result = response.json()
        # Dọn token rác TRƯỚC khi chấm `_dang_ngo`: nếu bản phiên âm chỉ toàn
        # token thì sau khi dọn nó thành rỗng và bị luật "quá ngắn" loại - đúng
        # hơn là để nguyên rồi tưởng khách có nói.
        text = _sua_nghe_nham(_don_token((result.get("text") or "").strip()))

        # Máy chủ nào không trả `segments` thì hai số này vắng; khi đó chỉ còn
        # lọc theo độ dài và mẫu câu. Đừng vì thiếu số mà bỏ luôn lượt của khách.
        doan = result.get("segments") or []
        return (text,
                max((d.get("no_speech_prob", 0.0) for d in doan), default=0.0),
                min((d.get("avg_logprob", 0.0) for d in doan), default=0.0))

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Phiên âm tiếng Việt. Trả chuỗi RỖNG nếu bản phiên âm đáng ngờ.

        Dùng `verbose_json` thay cho `json` để lấy `no_speech_prob` và
        `avg_logprob` của từng đoạn - không có hai số đó thì không phân biệt được
        "khách nói thật" với "mô hình bịa trên nhiễu".

        Chạy hai nước: có mồi từ vựng trước, không mồi để VỚT LẠI. Lý do là mồi
        lợi hại lẫn lộn, đo được cả hai chiều:

        Câu bán hàng (`scripts/do_moi_tu_vung.py --cau-mau`, qua 8kHz + AMR-NB):
            không mồi  CER 0.019, giữ từ khoá 4/6
            có mồi     CER 0.015, giữ từ khoá 5/6   <- mồi CÓ LỢI ("hãng mức"
                                                       -> "hạn mức")

        Bản ghi cuộc gọi thật, lời không có từ ngân hàng nào:
            không mồi  'có nghe theo anh nói không'      logprob -0.05, giữ
            có mồi     'ủa tôi nghe thấy anh nói không'  logprob -0.33, BỊ VỨT

        Mồi kéo bộ giải mã về phía văn bản ngân hàng, câu nào không thuộc miền đó
        thì bị kéo lệch rồi rớt bộ lọc. Mà HAI KIỂU HỎNG NÀY KHÔNG NGANG NHAU:
        nghe sai một từ thì LLM còn đoán được ý, còn mất trắng cả lượt thì khách
        nói xong AI im - đúng cái lỗi khó chịu nhất đã gặp nhiều lần.

        Nên: giữ mồi cho phần lợi, và khi mồi làm lượt bị vứt thì hỏi lại lần nữa
        KHÔNG mồi. Chỉ tốn thêm một lần gọi ở đúng những lượt vốn dĩ mất trắng.
        """
        # Đo độ dài TRƯỚC khi bọc WAV: bọc rồi thì phải bóc header ra mới tính
        # được, mà độ dài là thứ `_dang_ngo` cần để nới ngưỡng cho lượt ngắn.
        giay = len(audio_bytes) / (sample_rate * 2)
        if not audio_bytes[:4] == b"RIFF":
            audio_bytes = pcm_to_wav(audio_bytes, sample_rate=sample_rate)
        else:
            giay = max(0.0, (len(audio_bytes) - 44) / (sample_rate * 2))

        with Timer("STT", logger) as t:
            ket = await self._goi_whisper(audio_bytes, moi_tu_vung(settings.stt_vung_mien))
        if ket is None:
            return ""
        text, khong_tieng, tu_tin = ket

        ly_do = self._dang_ngo(text, khong_tieng, tu_tin, giay)
        if ly_do:
            vot = await self._goi_whisper(audio_bytes, "")
            if vot and not self._dang_ngo(vot[0], vot[1], vot[2], giay):
                logger.info("STT vớt lại KHÔNG mồi: '%s' (%s) -> '%s' (logprob "
                            "%.2f -> %.2f)", text[:40], ly_do, vot[0][:40],
                            tu_tin, vot[2])
                return vot[0]
            logger.info(f"STT bỏ lượt ({ly_do}): '{text[:60]}' ({t.elapsed_ms:.0f}ms)")
            return ""

        logger.info(f"STT result: '{text}' (no_speech {khong_tieng:.2f}, "
                    f"logprob {tu_tin:.2f}, {t.elapsed_ms:.0f}ms)")
        return text

    async def health_check(self) -> bool:
        try:
            resp = await self.client.get(f"{self.base_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()
