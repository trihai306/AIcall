"""Phát hiện hộp thư thoại (Điều 6: "Tắt máy khi vào hộp thư thoại").

Không có bộ dò này thì bot tư vấn hết cả kịch bản cho một hộp thư thoại: tốn
máy, tốn cước, và báo cáo ghi nhầm thành "đã tư vấn xong".

Ba dấu hiệu, không cái nào một mình đủ tin:

  1. LỜI CHÀO DÀI KHÔNG NGẮT — hộp thư thoại nói liền 8-15 giây rồi im hẳn.
     Người thật nói 1-3 giây ("A lô?", "Ai đấy ạ?") rồi CHỜ.
  2. TỪ KHOÁ trong bản ghi — "để lại lời nhắn", "sau tiếng bíp", "thuê bao quý
     khách vừa gọi"...
  3. TIẾNG BÍP — tone đơn tần quanh 1 kHz, kéo vài trăm mili giây.

Kết luận là hộp thư thoại khi: CÓ TỪ KHOÁ, hoặc (LỜI CHÀO DÀI **và** CÓ BÍP).

Vì sao đòi hai dấu hiệu ở nhánh sau: nhận nhầm NGƯỜI THẬT thành hộp thư thoại
là lỗi nặng hơn nhiều so với bỏ sót một hộp thư thoại. Bỏ sót thì mất mấy chục
giây cước; nhận nhầm thì cúp máy vào mặt một khách hàng đang nghe.
"""

import logging
import re
import unicodedata

import numpy as np

logger = logging.getLogger(__name__)

# Chỉ dò trong ngần này giây đầu cuộc gọi. Sau đó thì đã là hội thoại thật, và
# một câu khách nói tình cờ trùng từ khoá không được phép làm cúp máy.
CUA_SO_DO_S = 20.0

# Lời chào dài bao nhiêu giây thì đáng ngờ. 6s là ranh giới an toàn: người thật
# hiếm khi độc thoại quá 6 giây trước khi chờ phản hồi, còn lời chào hộp thư
# thoại của các nhà mạng VN đều dài hơn thế.
NGUONG_CHAO_DAI_S = 6.0

# Tiếng bíp: dải tần và độ dài
BIP_TAN_MIN = 800.0
BIP_TAN_MAX = 1700.0
BIP_TOI_THIEU_MS = 150.0
_NGUONG_TAP_TRUNG = 0.45   # bao nhiêu phần năng lượng phải nằm trong dải bíp
_NGUONG_IM = 0.01

# Từ khoá của lời chào hộp thư thoại / thông báo nhà mạng. So khớp trên bản ghi
# đã bỏ dấu, nên viết ở đây có dấu hay không đều được.
TU_KHOA = (
    "hop thu thoai",
    "hop thu tra loi",
    "de lai loi nhan",
    "de lai tin nhan",
    "sau tieng bip",
    "sau tieng beep",
    "thue bao quy khach vua goi",
    "thue bao quy khach",
    "hien khong lien lac duoc",
    "khong the ket noi",
    "tam thoi khong lien lac duoc",
    "vui long goi lai sau",
    "xin vui long goi lai",
    "the subscriber you have dialed",
    "leave a message",
    "after the tone",
    "is not available",
)


def _bo_dau(s: str) -> str:
    """'Hộp thư thoại' -> 'hop thu thoai'. Bản ghi STT hay rơi dấu, so khớp
    có dấu thì trượt đúng những lần cần bắt nhất."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d")
    return re.sub(r"\s+", " ", s).strip()


_TU_KHOA_SACH = tuple(_bo_dau(t) for t in TU_KHOA)


def co_tu_khoa(text: str) -> str:
    """Từ khoá hộp thư thoại đầu tiên khớp trong `text`, rỗng nếu không có."""
    sach = _bo_dau(text)
    if not sach:
        return ""
    for goc, khoa in zip(TU_KHOA, _TU_KHOA_SACH):
        if khoa in sach:
            return goc
    return ""


def co_tieng_bip(pcm: np.ndarray, sr: int = 8000) -> bool:
    """Trong đoạn tiếng này có tone đơn tần quanh 1 kHz không.

    Xét theo từng khung 30ms rồi đòi các khung có bíp phải liền nhau đủ dài:
    một khung đơn lẻ trùng dải tần chỉ là nhiễu, tiếng bíp thật kéo liên tục.
    """
    if pcm is None or len(pcm) == 0:
        return False
    x = np.asarray(pcm, dtype=np.float32)
    N = max(64, int(0.030 * sr))
    if len(x) < N:
        return False

    can_lien_tiep = max(1, int(BIP_TOI_THIEU_MS / 30.0))
    lien_tiep = 0
    cua_so = np.hanning(N)
    tan = np.fft.rfftfreq(N, 1.0 / sr)
    trong_dai = (tan >= BIP_TAN_MIN) & (tan <= BIP_TAN_MAX)

    for k in range(0, len(x) - N + 1, N):
        w = x[k:k + N]
        if np.sqrt((w ** 2).mean()) < _NGUONG_IM:
            lien_tiep = 0
            continue
        spec = np.abs(np.fft.rfft(w * cua_so)) ** 2
        tong = float(spec.sum())
        if tong <= 0:
            lien_tiep = 0
            continue
        if float(spec[trong_dai].sum()) / tong >= _NGUONG_TAP_TRUNG:
            lien_tiep += 1
            if lien_tiep >= can_lien_tiep:
                return True
        else:
            lien_tiep = 0
    return False


class BoDoHopThuThoai:
    """Theo dõi những giây đầu của một cuộc gọi và kết luận.

    Dùng: mỗi khung tiếng từ khách gọi `them_tieng`, mỗi bản ghi STT gọi
    `them_ban_ghi`, rồi đọc `la_hop_thu_thoai`.
    """

    def __init__(self, sr: int = 8000, cua_so_s: float = CUA_SO_DO_S):
        self.sr = sr
        self.cua_so_s = cua_so_s
        self.giay_da_nghe = 0.0
        self.doan_noi_dai_nhat = 0.0
        self._doan_hien_tai = 0.0
        self.co_bip = False
        self.tu_khoa = ""
        self.ket_luan = False
        self.ly_do = ""

    @property
    def con_do(self) -> bool:
        """Đã qua cửa sổ dò chưa. Hết cửa sổ thì thôi, đừng tốn CPU nữa."""
        return not self.ket_luan and self.giay_da_nghe < self.cua_so_s

    def them_tieng(self, pcm: np.ndarray, dang_noi: bool):
        """Một khung tiếng từ phía khách. `dang_noi` lấy từ VAD sẵn có."""
        if not self.con_do or pcm is None or len(pcm) == 0:
            return

        thoi_luong = len(pcm) / float(self.sr)
        self.giay_da_nghe += thoi_luong

        if dang_noi:
            self._doan_hien_tai += thoi_luong
            self.doan_noi_dai_nhat = max(self.doan_noi_dai_nhat, self._doan_hien_tai)
        else:
            self._doan_hien_tai = 0.0

        # Chỉ soi tìm bíp khi đã có lời chào dài: bíp một mình không kết luận
        # được gì (nhạc chờ, tiếng nền tổng đài cũng ra tone), nên soi sớm chỉ
        # tốn CPU trên đường găng của cuộc gọi.
        if not self.co_bip and self.doan_noi_dai_nhat >= NGUONG_CHAO_DAI_S:
            self.co_bip = co_tieng_bip(pcm, self.sr)

        self._chot()

    def them_ban_ghi(self, text: str):
        """Một bản ghi STT từ phía khách."""
        if not self.con_do:
            return
        if not self.tu_khoa:
            self.tu_khoa = co_tu_khoa(text)
        self._chot()

    def _chot(self):
        if self.ket_luan:
            return
        if self.tu_khoa:
            self.ket_luan = True
            self.ly_do = f'Bản ghi có cụm "{self.tu_khoa}"'
        elif self.doan_noi_dai_nhat >= NGUONG_CHAO_DAI_S and self.co_bip:
            self.ket_luan = True
            self.ly_do = (
                f"Nói liền {self.doan_noi_dai_nhat:.1f}s không ngắt và có tiếng bíp"
            )
        if self.ket_luan:
            logger.info(f"[hộp thư thoại] {self.ly_do}")

    @property
    def la_hop_thu_thoai(self) -> bool:
        return self.ket_luan

    def to_dict(self) -> dict:
        return {
            "la_hop_thu_thoai": self.ket_luan,
            "ly_do": self.ly_do,
            "doan_noi_dai_nhat": round(self.doan_noi_dai_nhat, 1),
            "co_bip": self.co_bip,
            "tu_khoa": self.tu_khoa,
            "giay_da_nghe": round(self.giay_da_nghe, 1),
        }
