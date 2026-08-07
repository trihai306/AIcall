import base64, io, sys, time, requests, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://localhost:8100/api/voices/test-tts"; STT="http://localhost:8178/inference"
S = requests.Session()          # TAI DUNG ket noi, giong backend
r = requests.post(TTS, data={"text":"Cho tôi hỏi lãi suất vay tín chấp hiện tại là bao nhiêu phần trăm một năm và vay tối đa được bao nhiêu tiền ạ","voice_name":"giong_test","fast":"false"}, timeout=180).json()
w, sr = sf.read(io.BytesIO(base64.b64decode(r["audio"])), dtype="float32")
if w.ndim > 1: w = w[:,0]
n16 = int(len(w)/sr*16000)
x = np.interp(np.linspace(0,len(w)-1,n16), np.arange(len(w)), w).astype("float32")
print("nguon: %.1f giay" % (len(x)/16000))

def wav_bytes(a):
    b = io.BytesIO(); sf.write(b, a, 16000, subtype="PCM_16", format="WAV"); return b.getvalue()

def call(wb):
    t0=time.perf_counter()
    resp = S.post(STT, files={"file":("a.wav",wb,"audio/wav")}, data={"language":"vi","response_format":"json"}, timeout=180)
    ms = (time.perf_counter()-t0)*1000
    try: txt = resp.json().get("text","")
    except Exception: txt = resp.text[:40]
    return ms, txt.strip()

call(wav_bytes(x[:16000]))      # lam am
print("%-8s %9s   %s" % ("độ dài", "STT", "nghe ra"))
for giay in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0):
    seg = x[:int(16000*giay)]
    if len(seg) < 1600: continue
    wb = wav_bytes(seg)
    best, txt = min((call(wb) for _ in range(3)), key=lambda t: t[0])
    print("%-8s %7.0f ms   %s" % ("%.1fs" % giay, best, txt[:52]))
