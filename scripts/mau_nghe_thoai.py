"""Xuất mẫu để NGHE: nfe thấp/cao, trước và sau khi qua đường thoại.

CER chỉ đo được nghe có ra chữ không, không đo được nghe có tự nhiên không.
Mà độ tự nhiên mới là thứ quyết định khách có thấy đang nói chuyện với máy.
"""
import asyncio, io, subprocess, sys, tempfile, wave
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
P = Path(r"C:\duan\chat-ai"); sys.path.insert(0, str(P))
import numpy as np

CAU = ("Dạ anh chị chuẩn bị chứng minh nhân dân và sao kê lương ba tháng gần nhất ạ. "
       "Lãi suất vay tín chấp từ sáu phẩy năm phần trăm một năm ạ.")

def doc(b):
    with wave.open(io.BytesIO(b)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype("float32")/32768, w.getframerate()

def ghi(x, sr):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x,-1,1)*32767).astype("<i2").tobytes())
    return buf.getvalue()

def qua_thoai(wav24):
    x, sr = doc(wav24)
    n = int(len(x)/sr*8000)
    x8 = np.interp(np.linspace(0,len(x)-1,n), np.arange(len(x)), x).astype("float32")
    with tempfile.TemporaryDirectory() as d:
        pi, pa, po = Path(d)/"i.wav", Path(d)/"m.amr", Path(d)/"o.wav"
        pi.write_bytes(ghi(x8, 8000))
        subprocess.run(["ffmpeg","-y","-i",str(pi),"-ar","8000","-ac","1",
                        "-c:a","libopencore_amrnb","-b:a","12.2k",str(pa)], capture_output=True)
        subprocess.run(["ffmpeg","-y","-i",str(pa),"-ar","8000","-ac","1",str(po)], capture_output=True)
        return po.read_bytes()

async def main():
    from backend.config import settings
    from backend.services.tts_service import F5TTSService
    tts = F5TTSService(); tts.load()
    cu = settings.f5tts_nfe_step
    await tts.synthesize("khởi động", use_cache=False)

    out = P / "logs" / "mau_nghe"; out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.wav"): f.unlink()

    for nfe in (8, 12, 16):
        settings.f5tts_nfe_step = nfe
        w = await tts.synthesize(CAU, use_cache=False)
        (out / f"nfe{nfe:02d}_goc24k.wav").write_bytes(w)
        (out / f"nfe{nfe:02d}_qua_dien_thoai.wav").write_bytes(qua_thoai(w))
        print(f"  nfe={nfe:2d}: đã xuất bản gốc 24kHz và bản qua đường thoại")
    settings.f5tts_nfe_step = cu
    print(f"\n{out}")

asyncio.run(main())
