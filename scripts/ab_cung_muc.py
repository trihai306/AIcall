"""A/B công bằng: chỉ khác nhau ở phần xử lý, mức âm lượng chỉnh cho bằng nhau.

So hai bản khác mức là so sai - to hơn 2dB thì tai luôn thấy hay hơn bất kể
chất lượng. Ở đây mọi bản đều đưa về đúng -19 dBFS rồi mới qua codec.
"""
import asyncio, io, subprocess, sys, tempfile, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np
from backend.services.audio_utils import resample_audio

DOAN = ("Dạ em chào anh chị ạ. Bên em đang có chương trình vay tín chấp lãi suất "
        "ưu đãi từ sáu phẩy năm phần trăm một năm. "
        "Hồ sơ rất đơn giản, anh chị chỉ cần căn cước công dân và sao kê lương "
        "ba tháng gần nhất ạ.")
MUC = -19.0

def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32")/32768, w.getframerate()

def ghi(x, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x,-1,1)*32767).astype("<i2").tobytes())
    return buf.getvalue()

def chuan_muc(x):
    r = float(np.sqrt((x**2).mean())) or 1e-9
    y = x * (10**(MUC/20) / r)
    d = float(np.abs(y).max())
    return (y * min(1.0, 0.95/d)).astype("float32") if d > 0.95 else y.astype("float32")

def qua_gsm(x8):
    with tempfile.TemporaryDirectory() as d:
        pi, pa, po = Path(d)/"i.wav", Path(d)/"m.amr", Path(d)/"o.wav"
        pi.write_bytes(ghi(x8, 8000))
        subprocess.run(["ffmpeg","-y","-i",str(pi),"-ar","8000","-ac","1",
                        "-c:a","libopencore_amrnb","-b:a","12.2k",str(pa)], capture_output=True)
        subprocess.run(["ffmpeg","-y","-i",str(pa),"-ar","8000","-ac","1",str(po)], capture_output=True)
        return po.read_bytes()

async def main():
    from backend.config import settings
    from backend.services.phone_call_service import toi_uu_cho_thoai
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    await tts.synthesize("khởi động", use_cache=False)
    out = P/"logs"/"ab_cung_muc"; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"): f.unlink()

    w = await tts.synthesize(DOAN, use_cache=False)
    x, sr = doc(w)
    (out/"A_goc_24kHz.wav").write_bytes(ghi(chuan_muc(x), sr))

    ban = {
        "B_thoai_khong_xu_ly": resample_audio(chuan_muc(x), sr, 8000),
    }
    goc_db, goc_hp = settings.phone_nang_do_ro_db, settings.phone_loc_tram_hz
    # chỉ lọc trầm, KHÔNG nâng dải - tách riêng hai tác động
    settings.phone_nang_do_ro_db = 0.0
    ban["C_chi_loc_tram"] = resample_audio(chuan_muc(toi_uu_cho_thoai(x, sr)), sr, 8000)
    # lọc trầm + nâng nhẹ
    settings.phone_nang_do_ro_db = 4.0
    ban["D_loc_tram_nang_4dB"] = resample_audio(chuan_muc(toi_uu_cho_thoai(x, sr)), sr, 8000)
    settings.phone_nang_do_ro_db = 6.0
    ban["E_loc_tram_nang_6dB"] = resample_audio(chuan_muc(toi_uu_cho_thoai(x, sr)), sr, 8000)
    settings.phone_nang_do_ro_db, settings.phone_loc_tram_hz = goc_db, goc_hp

    print(f"{'file':<26}{'RMS dBFS':>11}{'đỉnh':>8}")
    print("-" * 45)
    for ten, y in ban.items():
        y = chuan_muc(y)
        (out/f"{ten}.wav").write_bytes(qua_gsm(y))
        print(f"{ten:<26}{20*np.log10(np.sqrt((y**2).mean())):>11.1f}{np.abs(y).max():>8.3f}")
    print("-" * 45)
    print(f"\nMọi bản cùng {MUC} dBFS - khác biệt nghe được chỉ do xử lý, không do to nhỏ.")
    print(out)

asyncio.run(main())
