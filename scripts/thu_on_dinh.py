"""Cung mot cau sinh 5 lan - co ra CUNG MOT file khong?"""
import base64,hashlib,json,sys,urllib.parse,urllib.request
sys.stdout.reconfigure(encoding="utf-8")
TTS="http://127.0.0.1:8100/api/voices/test-tts"
CAU=("Em chào anh chị. Em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng "
     "VPBank. Em nhận được thông tin anh chị đang quan tâm đến gói vay thế chấp "
     "sổ đỏ bên em. Không biết hiện tại anh chị đang có nhu cầu vay để làm gì và "
     "dự kiến cần vay khoảng bao nhiêu ạ?")
def sinh():
    d=urllib.parse.urlencode({"text":CAU,"voice_name":"giong_heu"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=300) as r: return json.load(r)
bam=[]
for i in range(5):
    r=sinh()
    if r.get("error"): print("LOI",r["error"]); break
    w=base64.b64decode(r["audio"]); h=hashlib.md5(w).hexdigest()[:12]
    bam.append(h); print(f"  lan {i+1}: {h}  {r['duration_ms']/1000:.2f}s  {len(w)} byte")
print(f"\n-> {len(set(bam))} file KHAC NHAU tren {len(bam)} lan sinh")
print("   " + ("ON DINH TUYET DOI - cung chu luon ra cung tieng" if len(set(bam))==1
               else "VAN CON NGAU NHIEN"))
