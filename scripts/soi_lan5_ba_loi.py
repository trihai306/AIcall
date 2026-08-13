"""Ba thi nghiem cho ba loi cua Lan 5. Moi thi nghiem doi DUNG MOT bien."""
import base64, io, json, re, sys, urllib.parse, urllib.request, wave
import numpy as np
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"; GIONG="giong_heu"
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
        return json.load(r)
def song(b64):
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
        return w.getframerate(), np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
def lang(x,sr,nguong=0.02,toi_thieu_ms=60):
    o=int(sr*0.025); n=len(x)//o
    env=np.array([np.abs(x[i*o:(i+1)*o]).max() for i in range(n)])
    im=env<nguong; ra=[];i=0
    while i<n:
        if im[i]:
            j=i
            while j<n and im[j]: j+=1
            if (j-i)*25>=toi_thieu_ms: ra.append((i*25/1000,(j-i)*25))
            i=j
        else: i+=1
    return ra
def duoi(x,sr,ms=200):
    o=int(sr*0.005); k=ms//5
    return [float(np.abs(x[len(x)-(i+1)*o:len(x)-i*o]).max()) for i in range(k)][::-1]

print("THÍ NGHIỆM 1 — F5 có tự nghỉ ở dấu phẩy khi KHÔNG tách mảnh không?")
print("  (nếu CÓ thì bỏ tách mảnh được, hết giật cục mà vẫn còn chỗ ngắt)")
for nhan,t in (("tách như nay","Em là Dương,"),
               ("để NGUYÊN cụm","Em là Dương, chuyên viên tư vấn tín dụng.")):
    j=sinh(t)
    if j.get("error"): print("   LỖI",j["error"][:50]); continue
    sr,x=song(j["audio"]); q=lang(x,sr)
    print(f"   {nhan:<16} {j['duration_ms']/1000:5.2f}s  {j['so_manh']} mảnh  "
          f"quãng lặng bên trong: {', '.join(f'{a:.2f}s({b:.0f}ms)' for a,b in q) or 'KHÔNG CÓ'}")

print("\nTHÍ NGHIỆM 2 — thiếu dấu kết câu có làm âm cuối bị cắt không?")
for nhan,t in (("KHÔNG dấu cuối","Việc kéo dài thời gian vay sẽ giúp giảm áp lực trả gốc hàng tháng xuống rất nhiều"),
               ("CÓ dấu chấm","Việc kéo dài thời gian vay sẽ giúp giảm áp lực trả gốc hàng tháng xuống rất nhiều.")):
    j=sinh(t)
    if j.get("error"): print("   LỖI",j["error"][:50]); continue
    sr,x=song(j["audio"]); d=duoi(x,sr)
    print(f"   {nhan:<16} {j['duration_ms']/1000:5.2f}s  200ms cuối: "
          + "".join("█" if v>.3 else "▓" if v>.12 else "░" if v>.03 else "·" for v in d)
          + f"  mẫu cuối {abs(float(x[-1])):.4f}")

print("\nTHÍ NGHIỆM 3 — âm cuối tận cùng bằng N/NG có bị nuốt hơn không?")
for t in ("Anh chị chuẩn bị hồ sơ vay vốn.","Thời gian vay tối đa hai mươi lăm năm.",
          "Em xin phép gọi lại sau ạ.","Hạn mức lên đến năm trăm triệu đồng."):
    j=sinh(t)
    if j.get("error"): continue
    sr,x=song(j["audio"]); d=duoi(x,sr,150)
    cuoi=t.rstrip(".").split()[-1]
    print(f"   {cuoi:<8} {'':2}150ms cuối: "
          + "".join("█" if v>.3 else "▓" if v>.12 else "░" if v>.03 else "·" for v in d))
