import base64, sys, requests, unicodedata, re
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://localhost:8100/api/voices/test-tts"; STT="http://localhost:8178/inference"
PH = "Dạ anh chị cần chuẩn bị chứng minh nhân dân"
N = 10
bad = 0; times = []
print("=== lap %d lan cung mot cau (nfe=16) ===" % N)
for i in range(N):
    r = requests.post(TTS, data={"text":PH,"voice_name":"default","fast":"true"}, timeout=180).json()
    wav = base64.b64decode(r["audio"]); times.append(r["elapsed_ms"])
    t = requests.post(STT, files={"file":("a.wav",wav,"audio/wav")},
                      data={"language":"vi","response_format":"json"}, timeout=180)
    try: hyp = t.json().get("text","")
    except Exception: hyp = t.text
    ok = hyp.strip().lower().startswith("dạ")
    if not ok: bad += 1
    print("  %2d) %4dms  %s  %r" % (i+1, r["elapsed_ms"], "OK " if ok else "SAI", hyp.strip()[:52]))
print("\n  --> doc sai chu mo dau: %d/%d (%.0f%%) | thoi gian TB %.0f ms" % (bad, N, 100*bad/N, sum(times)/len(times)))
