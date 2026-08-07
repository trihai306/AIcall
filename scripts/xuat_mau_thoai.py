"""Xuất mẫu tiếng ĐÚNG NHƯ KHÁCH GỌI ĐIỆN NGHE, để nghe mà quyết.

Đi qua đúng đường sản phẩm: toi_uu_cho_thoai() -> hạ 8kHz -> codec AMR-NB
12.2kbps của GSM. Nghĩa là file xuất ra chính là thứ tới tai khách, không phải
bản gốc 24kHz.

Xuất nhiều mức nâng dải độ rõ để so cạnh nhau rồi chọn, thay vì chỉnh một mức
rồi nghe, không ưng lại chỉnh tiếp.

    python scripts/xuat_mau_thoai.py
    python scripts/xuat_mau_thoai.py --muc 0 4 6 9 12
"""

import argparse
import asyncio
import io
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# Đoạn hội thoại thật, đủ dài để nghe ra ngữ điệu chứ không chỉ một câu lẻ.
DOAN = (
    "Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp lãi suất "
    "ưu đãi từ sáu phẩy năm phần trăm một năm. "
    "Hạn mức cho vay lên đến năm trăm triệu đồng, thời hạn tối đa sáu mươi tháng. "
    "Hồ sơ rất đơn giản, anh chị chỉ cần căn cước công dân và sao kê lương "
    "ba tháng gần nhất ạ. "
    "Anh chị cần em tư vấn thêm về điều kiện nào khác không ạ?"
)


def doc_wav(b: bytes):
    import numpy as np
    with wave.open(io.BytesIO(b)) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return x.astype("float32") / 32768, sr


def ghi_wav(x, sr: int) -> bytes:
    import numpy as np
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def qua_gsm(x8, sr=8000) -> bytes:
    """Đẩy qua đúng codec AMR-NB 12.2kbps mà mạng GSM dùng, rồi giải mã ngược."""
    with tempfile.TemporaryDirectory() as d:
        pi, pa, po = Path(d) / "i.wav", Path(d) / "m.amr", Path(d) / "o.wav"
        pi.write_bytes(ghi_wav(x8, sr))
        for cmd in (
            ["ffmpeg", "-y", "-i", str(pi), "-ar", "8000", "-ac", "1",
             "-c:a", "libopencore_amrnb", "-b:a", "12.2k", str(pa)],
            ["ffmpeg", "-y", "-i", str(pa), "-ar", "8000", "-ac", "1", str(po)],
        ):
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:])
        return po.read_bytes()


async def main() -> int:
    import numpy as np

    ap = argparse.ArgumentParser()
    ap.add_argument("--muc", type=float, nargs="+", default=[0, 4, 6, 9],
                    help="Các mức nâng dải độ rõ (dB) cần xuất để so")
    ap.add_argument("--out", default=str(PROJECT / "logs" / "mau_thoai"))
    args = ap.parse_args()

    from backend.config import settings
    from backend.services.audio_utils import resample_audio
    from backend.services.phone_call_service import toi_uu_cho_thoai
    from backend.services.tts_service import F5TTSService

    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động", use_cache=False)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"):
        f.unlink()

    print(f"Sinh đoạn hội thoại ({len(DOAN)} ký tự) ...")
    wav24 = await tts.synthesize(DOAN, use_cache=False)
    x24, sr = doc_wav(wav24)
    print(f"  {len(x24)/sr:.1f} giây\n")

    # bản gốc 24kHz để đối chiếu
    (out / "0_goc_24kHz.wav").write_bytes(wav24)

    def nghieng(y, s):
        ph = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
        f = np.fft.rfftfreq(len(y), 1 / s)
        return float(ph[(f >= 1000) & (f < 3400)].sum()
                     / (ph[(f >= 100) & (f < 1000)].sum() or 1e-12))

    print(f"{'file':<34}{'độ nghiêng':>12}{'RMS dBFS':>11}{'đỉnh':>8}")
    print("-" * 65)

    # 1) hiện trạng nếu TẮT tối ưu - để thấy rõ khác biệt
    x8 = resample_audio(x24, sr, 8000)
    ten = "1_TAT_toi_uu.wav"
    (out / ten).write_bytes(qua_gsm(x8))
    print(f"{ten:<34}{nghieng(x8,8000):>12.3f}"
          f"{20*np.log10(np.sqrt((x8**2).mean())+1e-12):>11.1f}"
          f"{np.abs(x8).max():>8.3f}")

    # 2) từng mức nâng dải độ rõ
    goc_db = settings.phone_nang_do_ro_db
    for db in args.muc:
        settings.phone_nang_do_ro_db = db
        y = resample_audio(toi_uu_cho_thoai(x24, sr), sr, 8000)
        ten = f"2_nang_{int(db):02d}dB.wav"
        (out / ten).write_bytes(qua_gsm(y))
        dau = "  <-- đang dùng" if abs(db - goc_db) < 0.01 else ""
        print(f"{ten:<34}{nghieng(y,8000):>12.3f}"
              f"{20*np.log10(np.sqrt((y**2).mean())+1e-12):>11.1f}"
              f"{np.abs(y).max():>8.3f}{dau}")
    settings.phone_nang_do_ro_db = goc_db

    print("-" * 65)
    print(f"\nTất cả file 8kHz đều đã qua codec AMR-NB của GSM - đúng thứ khách nghe.")
    print(f"File 0_goc_24kHz.wav là bản chưa qua điện thoại, chỉ để đối chiếu.")
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
