"""Kho TIẾNG SẴN cho câu trả lời có chữ cố định.

Hai chỗ trong pipeline nói ra chữ đã soạn sẵn, không qua mô hình:
  - bảng hỏi-đáp khi khách hỏi gần đúng cách đã duyệt (`doc_thang`)
  - lượt thường gặp (chào, "ai đấy", "đang bận"... - `luot_thuong_gap`)

Trước 05-09-2026 hai chỗ này vẫn cắt mảnh rồi gọi F5 từng mảnh như câu do mô
hình sinh, dù chữ không đổi giữa các cuộc gọi. Cache trong RAM của
`F5TTSService.synthesize` chỉ 256 mục và mất khi khởi động lại.

Ở đây dựng tiếng MỘT LẦN cho cả câu, cất ra đĩa, lần sau phát thẳng:
  - không tốn GPU lúc khách đang chờ, tiếng tới sau STT + tra bảng
  - cả câu sinh trong một lượt nên không còn chỗ nối giữa mảnh -> hết chữ ngân
    và lệch tông ở chỗ nối (đúng thứ bên A đã nghe ở bản xuất và duyệt)

Cùng luật với câu đệm (`filler_store`): vân tay = chữ + giọng + nfe + tốc + câu
mẫu (+ PHIEN_BAN cách sinh). Đổi bất kỳ thứ nào là bản trên đĩa bị coi là hết
hạn và dựng lại - không thì khách nghe hai chất giọng trong một cuộc, log vẫn
sạch. Vân tay lấy qua `tts._van_tay_filler` để không có hai công thức.

Thư mục: data/tieng_san/<giọng>/<mã>__<vân tay>.wav

KHO MẢNH (09-10-2026). Tiếng của một câu trả lời vốn đã là nhiều MẢNH (mỗi mảnh
một câu, phẩy đã gộp) sinh riêng rồi nối lại - xem `dung_tieng_ca_cau`. Cất từng
mảnh theo CHỮ của nó (data/tieng_san/<giọng>/_manh/<vân tay>.wav) thì mảnh dùng
lại được giữa các câu trả lời khác nhau, và hai việc trước đây luôn trượt kho
giờ phát được ngay:
  - câu của LUẬT có con số ("vay 4 tháng thì chưa được...", "số tiền 310 triệu
    đồng..."): trước đây cả câu cất chung một mã luật, số nào nói sau đè số nói
    trước; giờ mỗi mảnh một tệp, ghép lại cho mọi tổ hợp con số.
  - câu của kho + CÂU HỎI DẪN DẮT: trước đây mỗi cặp (đáp án, câu hỏi) là một
    tệp riêng dựng lười, gần 9.000 đáp án x 4 câu hỏi nên gần như lần nào cũng
    trượt (đo 09-10: 1,2s mới ra tiếng). Giờ ghép tệp đáp án có sẵn với mảnh câu
    hỏi.
Thiếu vài mảnh CUỐI thì phát phần đầu ngay và dựng phần còn lại trong lúc khách
đang nghe (`tra_phan`).
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import numpy as np

from backend.config import settings
from backend.services.audio_utils import pcm_to_wav

logger = logging.getLogger(__name__)

THU_MUC_TIENG_SAN = Path("data/tieng_san")
SR = 24000


def gop_o_phay(manh: list[str]) -> list[str]:
    """Nối mảnh kết bằng dấu phẩy vào mảnh sau; giữ ranh giới dấu chấm.

    Y hệt nhánh `gop_phay` của bản xuất (`api/voices._ghep_nhu_pipeline`) và
    là mục tiêu mà đường thoại chỉ đạt được ~30% (phải chờ LLM nhả mảnh sau).
    Ở đây có sẵn cả câu nên gộp được 100%. Chỗ chấm KHÔNG gộp: bên A 17-08 bác
    "gộp hết" vì "ạ chưa ngắt xong".
    """
    ra: list[str] = []
    for m in manh:
        if ra and ra[-1].rstrip().endswith(","):
            ra[-1] = ra[-1].rstrip() + " " + m
        else:
            ra.append(m)
    return ra


def cat_manh(text: str) -> list[str]:
    """Các mảnh của một câu trả lời, đúng cách `dung_tieng_ca_cau` cắt để sinh."""
    from backend.pipeline.text_chunker import chia_ca_luot

    return gop_o_phay([m for m in chia_ca_luot(text or "") if any(c.isalnum() for c in m)])


def noi_tieng(cac: list[tuple[str, bytes]]) -> bytes:
    """Nối tiếng các phần theo thứ tự, chèn nhịp nghỉ theo dấu câu cuối phần TRƯỚC."""
    from backend.pipeline.text_chunker import nhip_nghi_sau

    khuc: list[np.ndarray] = []
    nghi_ms = 0.0
    for chu, wav in cac:
        if nghi_ms > 0:
            khuc.append(np.zeros(int(SR * nghi_ms / 1000), dtype=np.int16))
        khuc.append(np.frombuffer(wav[44:], dtype=np.int16))
        nghi_ms = nhip_nghi_sau(chu)
    if not khuc:
        khuc.append(np.zeros(int(SR * 0.05), dtype=np.int16))
    return pcm_to_wav(np.concatenate(khuc).tobytes(), sample_rate=SR)


async def dung_tieng_ca_cau(tts, text: str, voice: str, kho: "KhoTiengSan | None" = None) -> bytes:
    """Dựng tiếng cho CẢ câu trả lời, ghép y như pipeline nhưng gộp hết chỗ phẩy.

    Cắt bằng `chia_ca_luot` (nguồn duy nhất của luật cắt), chèn nhịp nghỉ vào
    ĐẦU mảnh sau theo `nhip_nghi_sau` như `streaming_pipeline`. Không dùng
    `fast` cho mảnh đầu: ở đây không ai chờ, lấy chất lượng đủ bước.
    """
    # Có `kho` thì từng mảnh lấy từ kho mảnh nếu đã có, sinh xong cất lại: cùng
    # chữ + cùng tham số cho ra đúng một tiếng (seed suy từ chữ), nên mảnh dùng
    # chung không làm bản ghép khác bản sinh liền.
    cac: list[tuple[str, bytes]] = []
    for m in cat_manh(text):
        b = kho.lay_manh(tts, m, voice) if kho is not None else None
        if b is None:
            b = await tts.synthesize(m, voice=voice, use_cache=False, fast=False)
            if kho is not None:
                kho.cat_manh_vao_kho(tts, m, voice, b)
        cac.append((m, b))
    return noi_tieng(cac)


def rut_quang_im(wav: bytes, toi_da_ms: int, nguong: float = 90.0) -> bytes:
    """Rút mọi quãng im BÊN TRONG câu dài hơn `toi_da_ms` về đúng `toi_da_ms`.

    Tiếng sẵn là nhiều mảnh F5 nối lại: mỗi mảnh mang lặng thừa ở đầu và đuôi,
    cộng nhịp nghỉ chèn giữa hai mảnh. Đo trên cuộc gọi thật 08-10-2026: giữa
    "hạn mức vay tín chấp cá nhân" và "lên đến 500 triệu đồng" im 640ms, câu
    khác tới 840ms - khách tả là "đang nói tự nhiên dứt cái". Rút ở LÚC PHÁT để
    khỏi dựng lại mười mấy nghìn tệp; giữ phần đầu và phần cuối quãng im nên
    đuôi âm trước và đầu âm sau không bị chạm.
    """
    if toi_da_ms <= 0 or len(wav) <= 44:
        return wav
    x = np.frombuffer(wav[44:], dtype=np.int16)
    khung = SR // 100                                   # 10ms
    n = len(x) // khung
    if n < 20:
        return wav
    rms = np.sqrt((x[:n * khung].astype(np.float32).reshape(n, khung) ** 2).mean(1))
    im = rms < nguong
    giu = max(1, toi_da_ms // 10)                       # số khung im được giữ
    lay = np.ones(n, dtype=bool)
    co_tieng = np.flatnonzero(~im)
    if len(co_tieng) == 0:
        return wav
    dau, cuoi = co_tieng[0], co_tieng[-1]
    i = dau
    while i <= cuoi:
        if im[i]:
            j = i
            while j <= cuoi and im[j]:
                j += 1
            if j - i > giu:
                nua = giu // 2
                lay[i + nua: j - (giu - nua)] = False   # bỏ phần GIỮA quãng im
            i = j
        else:
            i += 1
    if lay.all():
        return wav
    ra = np.concatenate([x[:n * khung].reshape(n, khung)[lay].reshape(-1), x[n * khung:]])
    return pcm_to_wav(ra.tobytes(), sample_rate=SR)


# Một PHẦN của câu trả lời: (mã kho hoặc None, chữ). Có mã thì tiếng là tệp cả
# câu cất theo mã (đáp án kho `hd_...`, lượt thường gặp `ltg_...`); không mã thì
# tiếng ghép từ kho mảnh theo chữ.
Phan = tuple[str | None, str]


class KhoTiengSan:
    def __init__(self, thu_muc: Path = THU_MUC_TIENG_SAN):
        self.thu_muc = Path(thu_muc)
        self._cache: dict[tuple[str, str, str], bytes] = {}
        self._dang_dung: set[tuple[str, str]] = set()
        self._manh: dict[tuple[str, str], bytes] = {}
        self._so_lan_cat = 0

    # ---- kho mảnh ---------------------------------------------------------
    def _duong_manh(self, voice: str, vt: str) -> Path:
        return self.thu_muc / voice / "_manh" / f"{vt}.wav"

    def lay_manh(self, tts, manh: str, voice: str) -> bytes | None:
        """Tiếng của MỘT mảnh (một câu) theo đúng chữ + giọng + tham số, hoặc None."""
        if not manh or not manh.strip():
            return None
        vt = tts._van_tay_filler(manh, voice)
        wav = self._manh.get((voice, vt))
        if wav is not None:
            return wav
        p = self._duong_manh(voice, vt)
        try:
            if p.exists():
                wav = p.read_bytes()
                self._manh[(voice, vt)] = wav
                return wav
        except OSError as e:
            logger.debug("Kho mảnh: không đọc được %s: %s", p, e)
        return None

    def cat_manh_vao_kho(self, tts, manh: str, voice: str, wav: bytes) -> None:
        if not wav or len(wav) <= 44:
            return
        vt = tts._van_tay_filler(manh, voice)
        self._manh[(voice, vt)] = wav
        p = self._duong_manh(voice, vt)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(wav)
        except OSError as e:
            logger.warning("Kho mảnh: không ghi được %s (vẫn giữ trong RAM): %s", p, e)
            return
        self._so_lan_cat += 1
        if self._so_lan_cat % 200 == 0:
            self._don_manh(p.parent)

    def _don_manh(self, thu_muc: Path) -> None:
        """Giữ kho mảnh dưới `tieng_san_manh_toi_da` tệp: bỏ tệp lâu nhất không đụng tới."""
        toi_da = int(getattr(settings, "tieng_san_manh_toi_da", 0) or 0)
        if toi_da <= 0:
            return
        try:
            tep = sorted(thu_muc.glob("*.wav"), key=lambda f: f.stat().st_mtime)
        except OSError:
            return
        for f in tep[:max(0, len(tep) - toi_da)]:
            f.unlink(missing_ok=True)

    async def dung_manh(self, tts, manh: str, voice: str) -> bytes | None:
        """Lấy tiếng một mảnh, chưa có thì sinh rồi cất. Lỗi trả None, không ném."""
        co = self.lay_manh(tts, manh, voice)
        if co is not None:
            return co
        try:
            wav = await tts.synthesize(manh, voice=voice, use_cache=False, fast=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("Kho mảnh: sinh %r hỏng: %s", manh[:40], e)
            return None
        self.cat_manh_vao_kho(tts, manh, voice, wav)
        return wav

    # ---- câu trả lời theo PHẦN --------------------------------------------
    def lay_phan(self, tts, phan: Phan, voice: str) -> bytes | None:
        """Tiếng của một phần nếu đã có ĐỦ, không sinh gì."""
        ma, chu = phan
        if ma:
            co = self.lay(tts, ma, chu, voice)
            if co is not None:
                return co
        manh = cat_manh(chu)
        cac = [(m, self.lay_manh(tts, m, voice)) for m in manh]
        if not cac or any(w is None for _, w in cac):
            return None
        return noi_tieng(cac) if len(cac) > 1 else cac[0][1]

    def tra_phan(self, tts, cac_phan: list[Phan], voice: str) -> tuple[bytes | None, int]:
        """`(tiếng của các phần ĐẦU đã có sẵn, số phần đó)`.

        Số phần bằng `len(cac_phan)` là cả câu có sẵn. Ít hơn thì người gọi phát
        phần đầu ngay và dựng các phần còn lại trong lúc khách nghe.
        """
        dau: list[tuple[str, bytes]] = []
        for phan in cac_phan:
            wav = self.lay_phan(tts, phan, voice)
            if wav is None:
                break
            dau.append((phan[1], wav))
        if not dau:
            return None, 0
        wav = noi_tieng(dau) if len(dau) > 1 else dau[0][1]
        return rut_quang_im(wav, settings.tieng_san_im_toi_da_ms), len(dau)

    async def dung_phan(self, tts, phan: Phan, voice: str) -> bytes | None:
        """Dựng (và cất) tiếng cho một phần. Dùng cho phần đuôi và bước dựng nền."""
        co = self.lay_phan(tts, phan, voice)
        if co is not None:
            return co
        ma, chu = phan
        if ma:
            return await self.dung_mot(tts, ma, chu, voice)
        cac: list[tuple[str, bytes]] = []
        for m in cat_manh(chu):
            wav = await self.dung_manh(tts, m, voice)
            if wav is None:
                return None
            cac.append((m, wav))
        if not cac:
            return None
        return noi_tieng(cac) if len(cac) > 1 else cac[0][1]

    def _duong_dan(self, voice: str, ma: str, vt: str) -> Path:
        return self.thu_muc / voice / f"{ma}__{vt}.wav"

    def lay(self, tts, ma: str, text: str, voice: str) -> bytes | None:
        """Tiếng đã dựng cho đúng (chữ, giọng, tham số) này, hoặc None."""
        if not text or not text.strip():
            return None
        vt = tts._van_tay_filler(text, voice)
        key = (voice, ma, vt)
        wav = self._cache.get(key)
        if wav is not None:
            return wav
        p = self._duong_dan(voice, ma, vt)
        if p.exists():
            wav = rut_quang_im(p.read_bytes(), settings.tieng_san_im_toi_da_ms)
            self._cache[key] = wav
            return wav
        return None

    async def dung_mot(self, tts, ma: str, text: str, voice: str,
                       xoa_cu: bool = True) -> bytes | None:
        """Dựng nếu chưa có, cất ra đĩa, trả tiếng. Lỗi thì trả None, không ném."""
        if not text or not text.strip():
            return None
        co = self.lay(tts, ma, text, voice)
        if co is not None:
            return co
        khoa = (voice, ma)
        if khoa in self._dang_dung:      # một lượt khác đang dựng đúng câu này
            return None
        self._dang_dung.add(khoa)
        try:
            t0 = time.perf_counter()
            wav = await dung_tieng_ca_cau(tts, text, voice)
            vt = tts._van_tay_filler(text, voice)
            p = self._duong_dan(voice, ma, vt)
            p.parent.mkdir(parents=True, exist_ok=True)
            if xoa_cu:
                for cu in p.parent.glob(f"{ma}__*.wav"):
                    if cu != p:
                        cu.unlink(missing_ok=True)
            p.write_bytes(wav)
            self._cache[(voice, ma, vt)] = rut_quang_im(
                wav, settings.tieng_san_im_toi_da_ms)
            wav = self._cache[(voice, ma, vt)]
            logger.info("Tiếng sẵn: dựng %r cho giọng %s trong %.0fms (%d ký tự)",
                        ma, voice, (time.perf_counter() - t0) * 1000, len(text))
            return wav
        except Exception as e:  # noqa: BLE001
            logger.warning("Tiếng sẵn: dựng %r hỏng, lượt sau vẫn đi F5: %s", ma, e)
            return None
        finally:
            self._dang_dung.discard(khoa)

    async def dung_nhieu(self, tts, cac: dict[str, str], voice: str) -> dict:
        """Dựng cả bảng lúc khởi động. Trả thống kê để log."""
        kq = {"dung": 0, "da_co": 0, "bo_qua": 0, "hong": 0}
        t0 = time.perf_counter()
        for ma, text in cac.items():
            if not text or not text.strip():
                kq["bo_qua"] += 1
                continue
            if self.lay(tts, ma, text, voice) is not None:
                kq["da_co"] += 1
                continue
            wav = await self.dung_mot(tts, ma, text, voice)
            kq["dung" if wav else "hong"] += 1
            await asyncio.sleep(0)   # nhường vòng lặp cho việc khác giữa hai câu
        kq["ms"] = round((time.perf_counter() - t0) * 1000)
        return kq


kho_tieng_san = KhoTiengSan()
