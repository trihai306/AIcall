# Do DONG THOI toc do va do chinh xac cua TTS o nfe 16 (fast) va nfe 12 (thuong).
# Cham diem bang chinh PhoWhisper - dung cach tac gia da lam.
import base64, io, sys, unicodedata, re, requests
sys.stdout.reconfigure(encoding="utf-8")
TTS = "http://localhost:8100/api/voices/test-tts"
STT = "http://localhost:8178/inference"

PHRASES = [
    "Dạ em chào anh chị",
    "Dạ lãi suất vay tín chấp hiện tại",
    "Dạ được ạ, em xin phép tư vấn thêm",
    "Vâng, để em kiểm tra lại thông tin",
    "Dạ anh chị cần chuẩn bị chứng minh nhân dân",
]

def norm(s):
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"[^\w\sàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", "", s).strip()

def cer(ref, hyp):
    ref, hyp = norm(ref), norm(hyp)
    if not ref: return 0.0
    d = [[0]*(len(hyp)+1) for _ in range(len(ref)+1)]
    for i in range(len(ref)+1): d[i][0] = i
    for j in range(len(hyp)+1): d[0][j] = j
    for i in range(1, len(ref)+1):
        for j in range(1, len(hyp)+1):
            d[i][j] = min(d[i-1][j]+1, d[i][j-1]+1, d[i-1][j-1] + (ref[i-1] != hyp[j-1]))
    return 100.0 * d[len(ref)][len(hyp)] / len(ref)

def run(text, fast):
    r = requests.post(TTS, data={"text": text, "voice_name": "default", "fast": str(fast).lower()}, timeout=180).json()
    wav = base64.b64decode(r["audio"])
    t = requests.post(STT, files={"file": ("a.wav", wav, "audio/wav")},
                      data={"language": "vi", "response_format": "json"}, timeout=180)
    try:    hyp = t.json().get("text", "")
    except Exception: hyp = t.text
    return r["elapsed_ms"], hyp.strip(), cer(text, hyp)

for fast, nfe in ((True, 16), (False, 12)):
    ms_all, cer_all = [], []
    print("\n===== nfe = %d  (%s) =====" % (nfe, "fast/mảnh đầu" if fast else "thường"))
    for p in PHRASES:
        try:
            ms, hyp, c = run(p, fast)
            ms_all.append(ms); cer_all.append(c)
            print("  %4dms  CER %5.1f%%  | nghe ra: %r" % (ms, c, hyp[:60]))
        except Exception as e:
            print("  LOI:", e)
    if ms_all:
        print("  --> trung binh: %.0f ms | CER %.1f%%" % (sum(ms_all)/len(ms_all), sum(cer_all)/len(cer_all)))
