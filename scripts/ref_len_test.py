import base64, io, sys, requests, numpy as np, soundfile as sf
sys.stdout.reconfigure(encoding="utf-8")
BASE="http://localhost:8100"; S=requests.Session()

CAU = ("Xin chào anh chị, em là nhân viên tư vấn của ngân hàng, rất vui được hỗ trợ anh chị hôm nay. "
       "Bên em đang có chương trình vay ưu đãi lãi suất chỉ từ sáu phẩy năm phần trăm một năm. "
       "Hạn mức cho vay lên đến năm trăm triệu đồng, thời hạn tối đa sáu mươi tháng. "
       "Hồ sơ rất đơn giản, anh chị chỉ cần căn cước công dân và sao kê lương ba tháng gần nhất. ")

def sinh(text):
    r = S.post(BASE+"/api/voices/test-tts", data={"text":text,"voice_name":"giong_ngan","fast":"false"}, timeout=300).json()
    w, sr = sf.read(io.BytesIO(base64.b64decode(r["audio"])), dtype="float32")
    return (w[:,0] if w.ndim>1 else w), sr

def upload(ten, wav, sr, text):
    b = io.BytesIO(); sf.write(b, wav, sr, subtype="PCM_16", format="WAV"); b.seek(0)
    r = S.post(BASE+"/api/voices/upload", files={"file":(ten+".wav", b.getvalue(), "audio/wav")},
               data={"name":ten, "ref_text":text}, timeout=300)
    return r.json()

# dung giong mau dai dan: 1x, 3x, 6x doan van tren
print("dang sinh giong mau...")
mau = {}
for lan, ten in ((1,"reflen1"), (3,"reflen3"), (6,"reflen6")):
    text = CAU * lan
    parts, sr = [], 24000
    for i in range(lan):
        w, sr = sinh(CAU)
        parts.append(w)
    wav = np.concatenate(parts)
    res = upload(ten, wav, sr, text.strip())
    mau[ten] = len(wav)/sr
    print("  %-9s %5.1f giay  %s" % (ten, mau[ten], "OK" if "error" not in res else res["error"][:50]))

print("\n=== do TTS cung mot cau, khac do dai giong mau ===")
TARGET = "dạ lãi suất vay tín chấp hiện tại là sáu phẩy năm phần trăm"
print("%-9s %8s %10s" % ("giọng mẫu", "dài", "TTS"))
for ten in ("giong_ngan","reflen1","reflen3","reflen6"):
    best=None
    for _ in range(3):
        r = S.post(BASE+"/api/voices/test-tts", data={"text":TARGET,"voice_name":ten,"fast":"true"}, timeout=600).json()
        if "elapsed_ms" not in r: print("  %s LOI: %s" % (ten, str(r)[:60])); best=None; break
        best = r["elapsed_ms"] if best is None else min(best, r["elapsed_ms"])
    if best is not None:
        d = mau.get(ten, 3.78)
        print("%-9s %6.1fs %8d ms" % (ten, d, best))
