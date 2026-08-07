import base64, io, sys, requests, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
TTS = "http://localhost:8100/api/voices/test-tts"
FILLERS = ["Dạ vâng ạ", "Dạ, em hiểu rồi ạ", "Vâng, để em xem ạ", "Dạ được ạ"]
print("=== do dai filler SAU khi cat lang ===")
ds = []
for p in FILLERS:
    r = requests.post(TTS, data={"text":p,"voice_name":"default","fast":"false"}, timeout=180).json()
    w, sr = sf.read(io.BytesIO(base64.b64decode(r["audio"])), dtype="float32")
    d = len(w)/sr*1000; ds.append(d)
    print("  %-22s %5.0f ms tieng" % ("'"+p+"'", d))
print("\n  ngan nhat %.0f ms | dai nhat %.0f ms | TTFA duong thoai ~1127 ms" % (min(ds), max(ds)))
print("  -> khoang lang con lai: %.0f ms (xau nhat) .. %.0f ms (tot nhat)" % (1127-min(ds), max(0,1127-max(ds))))
