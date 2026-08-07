import base64, io, sys, requests, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
TTS = "http://localhost:8100/api/voices/test-tts"
PHRASES = [
    "Dạ lãi suất vay tín chấp hiện tại",
    "là sáu phẩy năm phần trăm một năm ạ",
    "Anh chị có quan tâm đến sản phẩm này không",
    "Dạ em xin phép tư vấn thêm",
]
THR = 0.01   # nguong coi la im lang

print("%-42s %8s %10s %10s %9s" % ("câu", "tổng", "lặng đầu", "lặng cuối", "biên độ đầu"))
tot_lead = tot_tail = 0
for p in PHRASES:
    r = requests.post(TTS, data={"text":p,"voice_name":"default","fast":"true"}, timeout=180).json()
    wav, sr = sf.read(io.BytesIO(base64.b64decode(r["audio"])), dtype="float32")
    if wav.ndim > 1: wav = wav[:,0]
    amp = np.abs(wav)
    nz = np.nonzero(amp > THR)[0]
    if len(nz) == 0:
        print("  %s -> IM LANG HOAN TOAN" % p); continue
    lead = nz[0] / sr * 1000
    tail = (len(wav) - nz[-1]) / sr * 1000
    tot_lead += lead; tot_tail += tail
    # bien do 5ms dau tien -> click/pop neu bat dau dot ngot
    first5 = float(np.max(amp[:int(sr*0.005)])) if len(wav) > sr*0.005 else 0
    print("%-42s %6.0fms %8.0fms %9.0fms %9.4f" % (p[:40], len(wav)/sr*1000, lead, tail, first5))

n = len(PHRASES)
print("\n  Trung binh: lang dau %.0fms + lang cuoi %.0fms = %.0fms CHET moi ranh gioi mach"
      % (tot_lead/n, tot_tail/n, tot_lead/n + tot_tail/n))
