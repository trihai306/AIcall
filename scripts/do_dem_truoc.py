"""Đệm TRƯỚC câu khách có an toàn không - trước khi sửa frontend.

Cách chữa dự kiến: giữ vòng đệm ~500ms tiếng micro BẤT KỂ ngưỡng, lúc mở lượt
thì gửi kèm. Nhưng phần đệm đó chứa tiếng AI vọng lại (khi AI đang nói) hoặc
nền phòng. Phép đo này hỏi: thêm phần đó vào ĐẦU câu thì STT có tệ đi không?

Ba loại đệm: im lặng, nền nhiễu nhẹ, và TIẾNG AI thật hạ nhỏ (mô phỏng vọng
qua echoCancellation của trình duyệt, còn sót ~10-30%).
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
DEM_MS = [0, 300, 500, 800]

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
    # tiếng AI để làm nguồn vọng
    w = await tts.synthesize("Hạn mức vay tối đa là năm trăm triệu đồng ạ.",
                             voice=tts.default_voice_name(), use_cache=False)
    ai, sr = sf.read(io.BytesIO(w), dtype="float32")
    if ai.ndim > 1: ai = ai.mean(axis=1)
    rng = np.random.default_rng(0)

    loai = {
        "im lặng":      lambda n: np.zeros(n, np.float32),
        "nền nhiễu":    lambda n: (rng.normal(0, 0.004, n)).astype(np.float32),
        "vọng AI 15%":  lambda n: (ai[-n:] * 0.15).astype(np.float32) if n <= len(ai) else np.zeros(n, np.float32),
        "vọng AI 30%":  lambda n: (ai[-n:] * 0.30).astype(np.float32) if n <= len(ai) else np.zeros(n, np.float32),
    }
    tong = {(t, m): [] for t in loai for m in DEM_MS}
    for cau in CAU:
        w = await tts.synthesize(cau, voice=giong, use_cache=False)
        x, _ = sf.read(io.BytesIO(w), dtype="float32")
        if x.ndim > 1: x = x.mean(axis=1)
        print(f"\n--- {cau!r}")
        for ten, lam in loai.items():
            for m in DEM_MS:
                y = x if m == 0 else np.concatenate([lam(int(sr * m / 1000)), x])
                wav = pcm_to_wav((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes(), sample_rate=sr)
                ra = await stt.transcribe(wav)
                txt = (ra or {}).get("text", "") if isinstance(ra, dict) else str(ra or "")
                e = cer(cau, txt); tong[(ten, m)].append(e)
                if m and (e > 0.05 or ten.startswith("vọng")):
                    print(f"   {ten:<12} +{m:>3}ms -> CER {e:.3f}  {txt!r}")
    print("\n=== CER trung bình ===")
    for ten in loai:
        print("  " + ten.ljust(12) + "  ".join(
            f"+{m}ms {sum(tong[(ten,m)])/len(tong[(ten,m)]):.3f}" for m in DEM_MS))

asyncio.run(main())
