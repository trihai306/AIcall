"""Cắt cụt ĐẦU câu khách bao nhiêu thì PhoWhisper hỏng thế nào.

Giả thuyết: `xuLyCatLoi` trong frontend chỉ giữ những khung LIÊN TỤC vượt
ngưỡng cuối cùng (mọi khung trước một chỗ trũng đều bị xoá), nên khi AI đang
nói (ngưỡng cao) thì phần đầu câu khách bị vứt. Phép đo này lượng hoá thiệt hại.

Sinh câu khách bằng giong_heu (KHÔNG dùng giong_nam - nó tự nuốt chữ), cắt dần
đầu câu, cho STT nghe lại, so với lời gốc.
"""
import asyncio, io, sys, unicodedata
from pathlib import Path
import numpy as np, soundfile as sf
GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
sys.stdout.reconfigure(encoding="utf-8")
from backend.services.tts_service import F5TTSService
from backend.services.stt_service import STTService
from backend.services.audio_utils import pcm_to_wav

CAU = ["hạn mức được bao nhiêu", "cơ chế thế nào", "lãi suất bao nhiêu",
       "hạn mức vay tín chấp bao nhiêu", "thủ tục vay như nào"]
CAT_MS = [0, 100, 150, 200, 250, 300, 400]

def chuan(s):
    s = unicodedata.normalize("NFC", (s or "").lower().strip())
    return " ".join("".join(c for c in s if c.isalnum() or c.isspace()).split())

def cer(goc, ra):
    a, b = chuan(goc), chuan(ra)
    d = [[0]*(len(b)+1) for _ in range(len(a)+1)]
    for i in range(len(a)+1): d[i][0] = i
    for j in range(len(b)+1): d[0][j] = j
    for i in range(1, len(a)+1):
        for j in range(1, len(b)+1):
            d[i][j] = min(d[i-1][j]+1, d[i][j-1]+1, d[i-1][j-1]+(a[i-1] != b[j-1]))
    return d[len(a)][len(b)] / max(len(a), 1)

async def main():
    tts = F5TTSService(); tts.load()
    stt = STTService()
    giong = "giong_heu" if any(v["name"] == "giong_heu" for v in tts.list_voices()) else tts.default_voice_name()
    print("giong khach:", giong)
    tong = {c: [] for c in CAT_MS}
    for cau in CAU:
        w = await tts.synthesize(cau, voice=giong, use_cache=False)
        x, sr = sf.read(io.BytesIO(w), dtype="float32")
        if x.ndim > 1: x = x.mean(axis=1)
        print(f"\n--- {cau!r}  ({len(x)/sr:.2f}s)")
        for c in CAT_MS:
            y = x[int(sr * c / 1000):]
            wav = pcm_to_wav((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes(), sample_rate=sr)
            ra = await stt.transcribe(wav)
            txt = (ra or {}).get("text", "") if isinstance(ra, dict) else str(ra or "")
            e = cer(cau, txt)
            tong[c].append(e)
            print(f"   cat {c:>3}ms -> CER {e:.3f}  {txt!r}")
    print("\n=== CER trung binh theo do cat ===")
    for c in CAT_MS:
        print(f"  cat {c:>3}ms : {sum(tong[c])/len(tong[c]):.3f}")

asyncio.run(main())
