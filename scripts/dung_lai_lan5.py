"""Dung lai DUNG hai cau cua Lan 5 sau ba ban va, de nghe doi chieu."""
import base64, io, json, sys, urllib.parse, urllib.request, wave
import numpy as np
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts, dong_dau_cuoi
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
RA=Path(r"C:\Users\Admin\Desktop\Check giọng\Lan 5 - DA SUA")
T1="Em chào anh chị. Em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng VPBank. Em nhận được thông tin anh chị đang quan tâm đến gói vay thế chấp sổ đỏ bên em...... Không biết hiện tại anh chị đang có nhu cầu vay để làm gì và dự kiến cần vay khoảng bao nhiêu ạ?"
T2="Dạ, đối với mục đích kinh doanh hoặc tiêu dùng sửa nhà, ngân hàng em hỗ trợ thời gian vay tối đa lên tới 20 - 25 năm tùy gói. Việc kéo dài thời gian vay sẽ giúp giảm áp lực trả gốc hàng tháng xuống rất nhiều"
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
        return json.load(r)
def lang(x,sr,toi_thieu_ms=60):
    o=int(sr*0.025); n=len(x)//o
    env=np.array([np.abs(x[i*o:(i+1)*o]).max() for i in range(n)])
    im=env<0.02; ra=[];i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            if (j-i)*25>=toi_thieu_ms: ra.append((i*25/1000,(j-i)*25))
            i=j
        else: i+=1
    return ra
RA.mkdir(parents=True, exist_ok=True)
for ten,t in (("1 - het giat cuc chu Duong", T1), ("2 - het thua chu vang", T2)):
    manh=_cat_manh_nhu_pipeline(t)
    print(f"=== {ten}")
    for m in manh: print(f"   {len(m.split()):>2} từ | {dong_dau_cuoi(normalize_for_tts(m))}")
    j=sinh(t)
    if j.get("error"): print("   LỖI",j["error"][:60]); continue
    (RA/f"{ten}.wav").write_bytes(base64.b64decode(j["audio"]))
    with wave.open(io.BytesIO(base64.b64decode(j["audio"]))) as w:
        sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
    o=int(sr*0.005)
    duoi=[float(np.abs(x[len(x)-(i+1)*o:len(x)-i*o]).max()) for i in range(40)][::-1]
    print(f"   {len(x)/sr:.2f}s  {j['so_manh']} mảnh")
    print(f"   quãng lặng: {', '.join(f'{a:.2f}s({b:.0f}ms)' for a,b in lang(x,sr)) or 'không có'}")
    print("   200ms cuối: " + "".join("█" if v>.3 else "▓" if v>.12 else "░" if v>.03 else "·" for v in duoi))
    print()
print("File:", RA)
