"""Ghi âm cuộc gọi (Điều 6, mục Báo cáo: "Có ghi âm").

Ghi HAI KÊNH TÁCH RIÊNG rồi ghép thành file stereo:
    kênh trái  = tiếng khách (chiều lên, từ micro điện thoại)
    kênh phải  = tiếng bot   (chiều xuống, tiếng TTS thật sự đã phát ra)

Vì sao tách kênh chứ không trộn một kênh: nghe lại biết ngay ai đang nói kể cả
khi hai bên nói đè lên nhau, và sau này tách được kênh khách ra để chấm lại độ
chính xác của nhận dạng trên chính dữ liệu thật.

ĐỒNG BỘ THỜI GIAN: chiều lên là dòng liên tục 20ms/khung kể cả lúc im lặng, nên
nó chính là ĐỒNG HỒ. Mỗi khung khách tới thì lấy một khung bot nếu có, không có
thì chèn im lặng. Nhờ vậy hai kênh không bao giờ trôi khỏi nhau, không cần dấu
thời gian và không cần bù trừ gì.

CHI PHÍ: mọi thứ nặng (mã hoá, ghi đĩa) nằm ở một task nền. Vòng thu và vòng
phát chỉ `append` vào deque - vài trăm nano giây. Ghi thẳng file trong vòng thu
là tự ăn vào ngân sách độ trễ của cuộc gọi.
"""

import asyncio
import logging
import time
from collections import deque
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Định dạng lưu. Opus 8kHz stereo cho cuộc 3 phút ~ 0,3-0,9 MB tuỳ mức ồn;
# cùng thứ đó ở WAV thô là 5,6 MB. Chạy chiến dịch vài nghìn số thì khác biệt
# đó là vài GB.
DINH_DANG = ("OGG", "OPUS")
DINH_DANG_DU_PHONG = ("WAV", "PCM_16")   # libsndfile nào cũng ghi được

# Gom bao nhiêu khung mới ghi xuống đĩa một lần. 50 khung = 1 giây: đủ thưa để
# không quấy ổ đĩa, đủ dày để mất tối đa 1 giây nếu tiến trình bị giết.
_KHOI_GHI = 50

# Khung bot được phép TRƯỢT bao nhiêu khung so với vị trí đã đóng dấu trước khi
# bị coi là quá hạn. 25 khung = 500ms.
#
# Vì sao phải cho trượt: vòng phát KHÔNG gửi đều 20ms/khung. Đồng hồ Windows có
# bước ~15,6ms nên khung rời vòng phát theo CỤM, và mỗi lượt còn mở màn bằng một
# chùm `dem_mo_s` (250ms) bắn tức thì để máy có đệm. Bản cũ vứt mọi khung cùng
# vị trí trừ một, nên mỗi cụm 3 khung chỉ còn 1: đo trên bản ghi thật thì kênh
# AI giữ lại đúng 33% số khung đã phát, tiếng bị đục lỗ 40ms suốt câu và nghe
# như vỡ. Điện thoại thì vẫn nhận đủ (đệm mồi hấp thụ cụm) - chỉ BẢN GHI hỏng.
#
# Cho trượt thì cụm được rải ra các vị trí trống liền sau, giữ nguyên thứ tự và
# không mất khung nào. Trượt tối đa 500ms là đủ nuốt cả chùm mở màn lẫn jitter,
# mà vẫn chặn được lệch thật: quá 500ms nghĩa là hai chiều đã trôi khỏi nhau
# (đứt ổ cắm rồi nối lại chẳng hạn), lúc đó vứt mới đúng - giữ lại chỉ làm tiếng
# cũ dồn vào chỗ mới.
_TRUOT_TOI_DA = 25


class GhiAmCuocGoi:
    """Ghi một cuộc gọi. Tạo xong gọi `start()`, kết thúc gọi `stop()`."""

    def __init__(self, session_id: str, thu_muc: Path, sr: int = 8000,
                 mau_moi_khung: int = 160):
        self.session_id = session_id
        self.sr = sr
        self.mau_moi_khung = mau_moi_khung      # 160 mẫu = 20ms @ 8kHz
        self.duong_dan = self._dat_ten(thu_muc)

        self._khach: deque[np.ndarray] = deque()
        # Khung bot đi kèm VỊ TRÍ trên trục thời gian của kênh khách. Không gắn
        # vị trí thì hai kênh lệch nhau ngay khi có một nhịp trễ: bộ ghi ghép
        # "khung nào đang ở đầu hàng đợi", nên tiếng bot nói ở giây thứ 3 có thể
        # rơi vào giây thứ 0 của bản ghi. Đã đo được đúng lỗi đó.
        self._bot: deque[tuple[int, np.ndarray]] = deque()
        self._nhan_khach = 0        # tổng số khung khách từng nhận
        self._chi_so_ghi = 0        # vị trí khung khách sắp ghi
        self._task: asyncio.Task | None = None
        self._dung = asyncio.Event()
        self.running = False
        self.so_khung = 0
        self.loi = ""
        self.bat_dau_luc: float | None = None

    @staticmethod
    def _dat_ten(thu_muc: Path) -> Path:
        # Chia theo ngày: một thư mục vài chục nghìn file thì `ls` cũng treo,
        # mà xoá file cũ theo hạn lưu trữ cũng chỉ là xoá vài thư mục.
        ngay = time.strftime("%Y-%m-%d")
        return Path(thu_muc) / ngay

    # --- vòng đời -------------------------------------------------------

    async def start(self) -> bool:
        if self.running:
            return True
        try:
            self.duong_dan.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.loi = f"Không tạo được thư mục ghi âm: {e}"
            logger.warning(self.loi)
            return False
        self._dung.clear()
        self.running = True
        self.bat_dau_luc = time.time()
        self._task = asyncio.create_task(self._ghi(), name=f"ghiam-{self.session_id}")
        return True

    async def stop(self) -> dict:
        """Dừng và chốt file. Trả về {duong_dan, dung_luong, giay}."""
        if not self.running:
            return self._ket_qua()
        self.running = False
        self._dung.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning(f"[ghi âm {self.session_id}] không chốt file kịp 10s")
                self._task.cancel()
            except Exception as e:
                logger.warning(f"[ghi âm {self.session_id}] lỗi khi chốt: {e}")
        return self._ket_qua()

    def _ket_qua(self) -> dict:
        tep = self._tep_thuc_te()

        # KHÔNG có khung tiếng nào thì XOÁ file và báo là không có bản ghi.
        #
        # Container Ogg chỉ-có-header là file HỎNG: libsndfile trả "Supported
        # file format but file is malformed", và trình duyệt hiện một trình phát
        # gãy. Đã bắt được đúng lỗi này — cuộc gọi không có tiếng nào đi qua
        # (bấm số hỏng, khách cúp ngay) đẻ ra file 871 byte mà Báo cáo vẫn trỏ
        # tới như thể có bản ghi. Thà nói "không có bản ghi" còn hơn đưa ra một
        # file không mở được.
        if self.so_khung == 0:
            if tep is not None and tep.exists():
                try:
                    tep.unlink()
                except OSError as e:
                    logger.debug(f"Không xoá được bản ghi rỗng {tep}: {e}")
            return {"duong_dan": "", "dung_luong": 0, "giay": 0.0,
                    "loi": self.loi or "Cuộc gọi không có tiếng nào để ghi"}

        return {
            "duong_dan": str(tep) if tep and tep.exists() else "",
            "dung_luong": tep.stat().st_size if tep and tep.exists() else 0,
            "giay": round(self.so_khung * self.mau_moi_khung / self.sr, 1),
            "loi": self.loi,
        }

    def _tep_thuc_te(self) -> Path | None:
        for duoi in (".opus", ".wav"):
            p = self.duong_dan / f"{self.session_id}{duoi}"
            if p.exists():
                return p
        return None

    # --- nạp tiếng vào (gọi từ vòng thu / vòng phát) ---------------------

    def them_khach(self, pcm: np.ndarray):
        """Một khung tiếng khách. Đây là đồng hồ của bản ghi."""
        if self.running:
            self._khach.append(np.asarray(pcm, dtype=np.float32))
            self._nhan_khach += 1

    def them_bot(self, pcm: np.ndarray):
        """Một khung tiếng bot ĐÃ THẬT SỰ PHÁT RA, không phải tiếng đã sinh.

        Khác biệt quan trọng: tiếng bị bỏ khi khách cắt lời thì khách không nghe
        thấy, nên nó không được có mặt trong bản ghi.

        Đóng dấu vị trí ngay lúc nhận: đó là mốc thời gian thật của khung này
        trên trục của kênh khách, và là thứ giữ hai kênh khớp nhau.
        """
        if self.running:
            self._bot.append((self._nhan_khach, np.asarray(pcm, dtype=np.float32)))

    # --- task nền -------------------------------------------------------

    async def _ghi(self):
        import soundfile as sf

        dinh_dang, duoi = DINH_DANG, ".opus"
        tep = self.duong_dan / f"{self.session_id}{duoi}"
        try:
            f = sf.SoundFile(str(tep), mode="w", samplerate=self.sr,
                             channels=2, format=dinh_dang[0], subtype=dinh_dang[1])
        except Exception as e:
            # Bản libsndfile không có Opus: rơi về WAV thay vì mất bản ghi.
            logger.warning(f"[ghi âm] không mã hoá được Opus ({e}) — ghi WAV")
            dinh_dang, duoi = DINH_DANG_DU_PHONG, ".wav"
            tep = self.duong_dan / f"{self.session_id}{duoi}"
            try:
                f = sf.SoundFile(str(tep), mode="w", samplerate=self.sr,
                                 channels=2, format=dinh_dang[0], subtype=dinh_dang[1])
            except Exception as e2:
                self.loi = f"Không mở được file ghi âm: {e2}"
                logger.error(self.loi)
                return

        im_lang = np.zeros(self.mau_moi_khung, dtype=np.float32)
        try:
            with f:
                while True:
                    khoi = self._lay_khoi(im_lang)
                    if khoi is not None:
                        # Ghi đĩa là chặn: đẩy sang luồng khác để vòng sự kiện
                        # (đang phục vụ chính cuộc gọi này) không phải chờ.
                        await asyncio.to_thread(f.write, khoi)
                    elif self._dung.is_set() and not self._khach:
                        break
                    else:
                        await asyncio.sleep(0.2)
        except Exception as e:
            self.loi = f"Ghi âm hỏng giữa chừng: {e}"
            logger.warning(f"[ghi âm {self.session_id}] {self.loi}", exc_info=True)

    def _lay_khoi(self, im_lang: np.ndarray) -> np.ndarray | None:
        """Ghép `_KHOI_GHI` khung thành mảng (n, 2). None nếu chưa đủ dữ liệu.

        Kênh bot được đặt theo VỊ TRÍ đã đóng dấu lúc nhận, không phải theo thứ
        tự trong hàng đợi — xem `them_bot`.
        """
        san_co = len(self._khach)
        if san_co == 0:
            return None
        if san_co < _KHOI_GHI and not self._dung.is_set():
            return None

        so_khung = min(san_co, _KHOI_GHI)
        trai, phai = [], []
        for _ in range(so_khung):
            k = self._khach.popleft()
            i = self._chi_so_ghi
            self._chi_so_ghi += 1

            # Bỏ khung bot quá hạn - nhưng chỉ khi đã lệch QUÁ XA. Lệch vài
            # chục mili giây là nhịp không đều của vòng phát chứ không phải sai
            # đồng bộ, vứt nó là đục thủng tiếng AI (xem `_TRUOT_TOI_DA`).
            while self._bot and self._bot[0][0] < i - _TRUOT_TOI_DA:
                self._bot.popleft()

            b = im_lang
            if self._bot and self._bot[0][0] <= i:
                b = self._bot.popleft()[1]

            # Hai chiều có thể lệch độ dài khung (tần số lấy mẫu khác nhau đã
            # được đổi trước khi vào đây, nhưng khung cuối hay bị cụt): cắt/đệm
            # về đúng độ dài chuẩn để mảng stereo không vỡ.
            trai.append(_chuan_do_dai(k, self.mau_moi_khung))
            phai.append(_chuan_do_dai(b, self.mau_moi_khung))

        self.so_khung += so_khung
        return np.stack([np.concatenate(trai), np.concatenate(phai)], axis=1)


def _chuan_do_dai(x: np.ndarray, n: int) -> np.ndarray:
    if len(x) == n:
        return x
    if len(x) > n:
        return x[:n]
    return np.concatenate([x, np.zeros(n - len(x), dtype=np.float32)])


# --- dọn file cũ --------------------------------------------------------------

def thong_ke(thu_muc: Path) -> dict:
    """Bản ghi đang chiếm bao nhiêu chỗ."""
    goc = Path(thu_muc)
    if not goc.exists():
        return {"so_file": 0, "dung_luong": 0, "so_ngay": 0}
    so_file = tong = 0
    ngay = set()
    for p in goc.rglob("*"):
        if p.is_file() and p.suffix in (".opus", ".wav"):
            so_file += 1
            tong += p.stat().st_size
            ngay.add(p.parent.name)
    return {"so_file": so_file, "dung_luong": tong, "so_ngay": len(ngay)}


def don_file_cu(thu_muc: Path, giu_ngay: int) -> dict:
    """Xoá bản ghi cũ hơn `giu_ngay` ngày. Trả về số file và dung lượng đã xoá."""
    goc = Path(thu_muc)
    if not goc.exists() or giu_ngay <= 0:
        return {"da_xoa": 0, "giai_phong": 0}

    han = time.time() - giu_ngay * 86400
    da_xoa = giai_phong = 0
    for p in goc.rglob("*"):
        if not (p.is_file() and p.suffix in (".opus", ".wav")):
            continue
        try:
            if p.stat().st_mtime < han:
                giai_phong += p.stat().st_size
                p.unlink()
                da_xoa += 1
        except OSError as e:
            logger.warning(f"Không xoá được {p}: {e}")
    # Dọn thư mục ngày đã rỗng
    for d in sorted(goc.iterdir(), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
            except OSError:
                pass
    return {"da_xoa": da_xoa, "giai_phong": giai_phong}
