"""Kỹ thuật tăng tuần hoàn còn tác dụng ở bitrate THẤP không?

Vì sao cần: mọi số liệu trước nay đo ở AMR-NB 12.2 kbps - chế độ mạng chỉ dùng
khi sóng tốt. Nhưng cuộc gọi thật đo được chạy trên EDGE (`gsm.network.type`
báo `EDGE` đúng lúc nối máy), và ở đó nhà mạng hạ xuống 7.4k hoặc 5.9k. Bitrate
càng thấp thì sổ mã đại số càng thưa, tiếng càng thô - nên phải kiểm lại xem
kỹ thuật có còn ăn thua ở điều kiện thật hay không.

    C:/duan/chat-ai/.venv/python.exe scripts/thu_bitrate_thap.py
"""

import asyncio
import io
import subprocess
import sys
import tempfile
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

CAU = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp "
       "lãi suất ưu đãi từ sáu phẩy năm phần trăm một năm.")

# Các chế độ AMR-NB. Mạng chọn theo chất lượng sóng.
CHE_DO = [("12.2k", "sóng tốt (3G/GSM đầy vạch)"),
          ("7.40k", "sóng trung bình"),
          ("5.90k", "sóng yếu / EDGE tải cao"),
          ("4.75k", "sóng rất yếu")]


def qua_amr_bitrate(x8: np.ndarray, bitrate: str) -> np.ndarray:
    from tang_tuan_hoan import doc_wav, ghi_wav
    with tempfile.TemporaryDirectory() as d:
        vao, amr, ra = (Path(d) / n for n in ("i.wav", "m.amr", "o.wav"))
        ghi_wav(vao, x8, 8000)
        for lenh in (
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(vao),
             "-ar", "8000", "-ac", "1", "-c:a", "libopencore_amrnb",
             "-b:a", bitrate, str(amr)],
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(amr),
             "-ar", "8000", "-ac", "1", str(ra)],
        ):
            r = subprocess.run(lenh, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or "")[:200])
        return doc_wav(ra)[0]


async def main() -> int:
    from backend.services import phone_call_service as PS
    from backend.services.audio_utils import resample_audio
    from backend.services.tts_service import F5TTSService
    from tang_tuan_hoan import do_hnr, do_phang_pho, doc_wav, ghi_wav, resample

    tts = F5TTSService()
    tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    w = await tts.synthesize(CAU, use_cache=False)
    with wave.open(io.BytesIO(w)) as f:
        sr = f.getframerate()
        x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    x = x.astype(np.float32) / 32768

    # đúng chuỗi đường tiếng hiện tại: chuẩn mức -> 8kHz -> (tăng tuần hoàn)
    goc = resample_audio(PS.chuan_muc_thoai(x), sr, 8000)
    xu = PS.tang_tuan_hoan(goc, 8000)

    # mốc người thật để so
    ref, srr = doc_wav(PROJECT / "models/tts/ref_voices/giong_ngan.wav")
    ref8 = resample(ref, srr, 8000)

    out = PROJECT / "logs" / "bitrate_thap"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"):
        f.unlink()

    print(f"\n  {'chế độ':<9}{'người thật':>12}{'TTS thường':>12}"
          f"{'TTS + tuần hoàn':>17}{'chênh':>8}")
    print("  " + "-" * 62)
    for br, ghi_chu in CHE_DO:
        h_ref = do_hnr(qua_amr_bitrate(ref8, br), 8000)
        y_goc = qua_amr_bitrate(goc, br)
        y_xu = qua_amr_bitrate(xu, br)
        h_g, h_x = do_hnr(y_goc, 8000), do_hnr(y_xu, 8000)
        ghi_wav(out / f"{br}_thuong__qua_dien_thoai.wav", y_goc, 8000)
        ghi_wav(out / f"{br}_tuan_hoan__qua_dien_thoai.wav", y_xu, 8000)
        print(f"  {br:<9}{h_ref:>12.2f}{h_g:>12.2f}{h_x:>17.2f}"
              f"{h_x - h_g:>+8.2f}")
    print("  " + "-" * 62)
    print(f"  {'':<9}{'':>12}{'':>12}{'(dB HNR sau AMR)':>17}")
    for br, ghi_chu in CHE_DO:
        print(f"    {br:<8} {ghi_chu}")
    print(f"\n  Mẫu nghe: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
