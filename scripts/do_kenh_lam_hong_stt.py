"""Nghe sai lời khách: mất ở khâu nào? Tách từng chặng của đường thoại.

Người dùng báo "nghe không đúng với lời khách nói". Trước khi sửa phải biết mất
ở đâu, nên dựng câu có LỜI GỐC BIẾT TRƯỚC rồi cho đi qua từng chặng, chấm bằng
CER (tỉ lệ sai ký tự).

Bốn chặng cộng dồn:
    1. gốc 24kHz              - mốc trên, STT ăn tiếng sạch
    2. hạ 8kHz                - mất dải trên 4kHz, nơi chứa phần lớn phụ âm xát
    3. + bộ mã AMR-NB         - đúng thứ mạng làm với tiếng
    4. + nâng lại 16kHz       - đúng thứ STT nhận được trong cuộc gọi thật

Chặng nào làm CER nhảy vọt thì đó là chỗ đáng sửa. Cũng đo riêng vài TỪ KHOÁ
của kịch bản bán hàng - sai "lãi suất" tai hại hơn sai một từ đệm.

    python scripts/do_kenh_lam_hong_stt.py
"""

import asyncio
import difflib
import io
import sys
import wave
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CAU = [
    "Cho anh hỏi lãi suất vay tín chấp bao nhiêu",
    "Anh muốn vay hai trăm triệu trong ba mươi sáu tháng",
    "Cần những giấy tờ gì để làm hồ sơ",
    "Anh có căn cước công dân và sao kê lương rồi",
    "Hạn mức tối đa của bên em là bao nhiêu",
]
# từ khoá quan trọng của kịch bản - sai mấy từ này là hỏng cả lượt tư vấn
TU_KHOA = ["lãi suất", "tín chấp", "căn cước", "sao kê", "hạn mức", "hồ sơ"]


def cer(goc: str, ra: str) -> float:
    a = "".join(c for c in goc.lower() if c.isalnum() or c == " ").split()
    b = "".join(c for c in ra.lower() if c.isalnum() or c == " ").split()
    a, b = " ".join(a), " ".join(b)
    return 1.0 - difflib.SequenceMatcher(None, a, b).ratio() if a else 1.0


def doc(b: bytes):
    with wave.open(io.BytesIO(b)) as w:
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                .astype(np.float32) / 32768), w.getframerate()


async def main() -> int:
    from backend.services.audio_utils import resample_audio, resample_lien_tuc
    from backend.services.stt_service import STTService
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import lay_bo_ma_amr

    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    stt = STTService()
    qua_amr, _ = lay_bo_ma_amr()

    async def chep(x: np.ndarray, sr: int) -> str:
        y = resample_audio(x, sr, 16000) if sr != 16000 else x
        pcm = (np.clip(y, -1, 1) * 32767).astype("<i2").tobytes()
        return await stt.transcribe(pcm, sample_rate=16000)

    ten = ["1. gốc 24kHz", "2. hạ 8kHz", "3. + AMR-NB", "4. + nâng 16kHz"]
    tong = {t: [] for t in ten}
    mat_tu_khoa = {t: 0 for t in ten}
    co_tu_khoa = 0

    for cau in CAU:
        w = await tts.synthesize(cau, use_cache=False)
        x24, sr = doc(w)
        x8 = resample_audio(x24, sr, 8000)
        x8amr = qua_amr(x8)
        x16 = resample_lien_tuc(x8amr, 8000, 16000)

        kq = {}
        kq[ten[0]] = await chep(x24, sr)
        kq[ten[1]] = await chep(x8, 8000)
        kq[ten[2]] = await chep(x8amr, 8000)
        kq[ten[3]] = await chep(x16, 16000)

        tk = [t for t in TU_KHOA if t in cau.lower()]
        co_tu_khoa += len(tk)
        print(f"\n  gốc: {cau!r}")
        for t in ten:
            e = cer(cau, kq[t])
            tong[t].append(e)
            thieu = [k for k in tk if k not in kq[t].lower()]
            mat_tu_khoa[t] += len(thieu)
            dau = f"  MẤT: {', '.join(thieu)}" if thieu else ""
            print(f"    {t:<17} CER {e:.3f}  {kq[t][:56]!r}{dau}")

    print(f"\n  {'=' * 66}")
    print(f"  {'chặng':<20}{'CER TB':>9}{'tăng thêm':>12}{'từ khoá mất':>14}")
    print("  " + "-" * 66)
    truoc = None
    for t in ten:
        tb = float(np.mean(tong[t]))
        them = "" if truoc is None else f"{tb - truoc:+.3f}"
        print(f"  {t:<20}{tb:>9.3f}{them:>12}"
              f"{mat_tu_khoa[t]:>10}/{co_tu_khoa}")
        truoc = tb
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
