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
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import numpy as np

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


async def dung_tieng_ca_cau(tts, text: str, voice: str) -> bytes:
    """Dựng tiếng cho CẢ câu trả lời, ghép y như pipeline nhưng gộp hết chỗ phẩy.

    Cắt bằng `chia_ca_luot` (nguồn duy nhất của luật cắt), chèn nhịp nghỉ vào
    ĐẦU mảnh sau theo `nhip_nghi_sau` như `streaming_pipeline`. Không dùng
    `fast` cho mảnh đầu: ở đây không ai chờ, lấy chất lượng đủ bước.
    """
    from backend.pipeline.text_chunker import chia_ca_luot, nhip_nghi_sau

    manh = gop_o_phay([m for m in chia_ca_luot(text) if any(c.isalnum() for c in m)])
    khuc: list[np.ndarray] = []
    nghi_ms = 0.0
    for m in manh:
        b = await tts.synthesize(m, voice=voice, use_cache=False, fast=False)
        pcm = np.frombuffer(b[44:], dtype=np.int16)
        if nghi_ms > 0:
            khuc.append(np.zeros(int(SR * nghi_ms / 1000), dtype=np.int16))
        khuc.append(pcm)
        nghi_ms = nhip_nghi_sau(m)
    if not khuc:
        khuc.append(np.zeros(int(SR * 0.05), dtype=np.int16))
    return pcm_to_wav(np.concatenate(khuc).tobytes(), sample_rate=SR)


class KhoTiengSan:
    def __init__(self, thu_muc: Path = THU_MUC_TIENG_SAN):
        self.thu_muc = Path(thu_muc)
        self._cache: dict[tuple[str, str, str], bytes] = {}
        self._dang_dung: set[tuple[str, str]] = set()

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
            wav = p.read_bytes()
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
            self._cache[(voice, ma, vt)] = wav
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
