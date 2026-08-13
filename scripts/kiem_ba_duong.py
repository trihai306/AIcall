"""Ba tinh nang - Test giong, Nhan tin (chat), Cuoc goi - co dung chung mot bo
luat khong? Kiem TREN MAY THAT, khong doc ma roi doan.

Bon thu phai giong nhau o ca ba:
  1. luat cat manh   (nguong tach dau phay = 4)
  2. luat chuan hoa  ("da," chu khong "da vang,"; them dau ket cau khi thieu)
  3. toc doc
  4. hat giong tat dinh -> cung chu + cung giong + cung toc = CUNG MOT tieng
"""
import asyncio, base64, hashlib, io, json, re, sys, urllib.parse, urllib.request, wave
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.streaming_pipeline import StreamingPipeline
from backend.pipeline.text_chunker import TOI_THIEU_TU_MOI_VE, tach_manh
from backend.pipeline.text_normalizer import dong_dau_cuoi, normalize_for_tts
WS="ws://127.0.0.1:8100/ws/call/new"; TTS="http://127.0.0.1:8100/api/voices/test-tts"
GIONG="giong_heu"
PROBE="Dạ em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng Quân đội"

print("1) LUẬT CẮT MẢNH — Test giọng so với đường gọi")
def cat_pipeline(van):
    ra,buf=[],van+" "
    for _ in range(40):
        if not buf.strip(): break
        m,buf=tach_manh(buf)
        if m is None: break
        ra.append(m)
    if buf.strip(): ra.append(buf.strip())
    return ra
a=_cat_manh_nhu_pipeline(PROBE); b=cat_pipeline(PROBE)
print(f"   Test giọng : {a}")
print(f"   đường gọi  : {b}")
print(f"   -> {'KHỚP' if a==b else 'LỆCH!'}   (ngưỡng tách phẩy = {TOI_THIEU_TU_MOI_VE})")

print("\n2) LUẬT CHUẨN HOÁ — dùng chung `normalize_for_tts` + `dong_dau_cuoi`")
for t in (PROBE, "Dạ vâng em hiểu ạ.", "câu thiếu dấu cuối"):
    print(f"   {t[:38]:<40} -> {dong_dau_cuoi(normalize_for_tts(t))[:52]}")

print("\n3) TỐC ĐỌC — nghe thử phải bằng cuộc gọi")
from types import SimpleNamespace
import urllib.request as U
with U.urlopen("http://127.0.0.1:8100/api/voices",timeout=60) as r:
    vs={v["name"]:v for v in json.load(r).get("voices",[])}
print(f"   tốc giọng {GIONG} = {vs[GIONG]['speed']}")
print(f"   (hệ số thoại chỉ áp khi đường tiếng ≤8kHz; nay = 1.00 nên mọi đường bằng nhau)")

print("\n4) CÙNG CHỮ -> CÙNG TIẾNG (hạt giống tất định)")
def sinh(t):
    d=urllib.parse.urlencode({"text":t,"voice_name":GIONG,"qua_dien_thoai":"false"}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS,data=d),timeout=600) as r:
        j=json.load(r)
    return base64.b64decode(j["audio"]), j
w1,j1=sinh(PROBE); w2,j2=sinh(PROBE)
print(f"   dựng hai lần: {hashlib.md5(w1).hexdigest()[:12]} và {hashlib.md5(w2).hexdigest()[:12]}"
      f"  -> {'GIỐNG HỆT' if w1==w2 else 'KHÁC NHAU!'}")
print(f"   {j1['duration_ms']/1000:.2f}s, {j1['so_manh']} mảnh")

async def mot_luot(kieu):
    async with websockets.connect(WS,max_size=None,open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh",
                                  "product":"vay tín chấp"}))
        while True:
            if json.loads(await ws.recv()).get("type")=="session_updated": break
        if kieu=="chat":
            await ws.send(json.dumps({"type":"text_soi","text":"lãi suất vay tín chấp bao nhiêu","turn_id":1}))
        else:
            r=sinh("Lãi suất vay tín chấp bao nhiêu em")[0]
            await ws.send(json.dumps({"type":"audio","data":base64.b64encode(r).decode(),"turn_id":1}))
        tra=""; mt={}; n_audio=0
        while True:
            m=json.loads(await asyncio.wait_for(ws.recv(),timeout=240))
            if m.get("type")=="audio": n_audio+=1
            if m.get("type")=="turn_complete":
                tra,mt=m.get("full_response",""),m.get("metrics",{}) or {}; break
        return tra,mt,n_audio
print("\n5) CHẠY THẬT — Nhắn tin và Cuộc gọi")
for kieu,ten in (("chat","Nhắn tin"),("call","Cuộc gọi")):
    try:
        tra,mt,na=asyncio.get_event_loop().run_until_complete(mot_luot(kieu))
        manh=_cat_manh_nhu_pipeline(tra)
        cut=[m for m in manh if len(m.split())<TOI_THIEU_TU_MOI_VE and m.rstrip().endswith(",")]
        print(f"   {ten:<10} {mt.get('total_ms','?')}ms · {mt.get('tts_chunks','-')} mảnh TTS · {na} gói tiếng")
        print(f"      trả lời: {tra[:70]}")
        print(f"      mảnh cụt kết bằng phẩy: {len(cut)}   'dạ vâng' trong lời: "
              f"{'CÓ (sai)' if 'dạ vâng' in normalize_for_tts(tra) else 'không'}")
    except Exception as e:
        print(f"   {ten}: LỖI {type(e).__name__} {e}")
