"""Soi ky hai con so dang ngo trong ban 100 luot:
   1. am tiet cuoi manh sai 37%  -> sai THAT hay cham nham?
   2. chu >800 am tiet/phut      -> doc voi THAT hay do het co so do?
"""
import asyncio, base64, io, json, re, sys, unicodedata, wave
from collections import Counter
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
from backend.api.voices import _cat_manh_nhu_pipeline
from backend.pipeline.text_normalizer import normalize_for_tts
from whisper_server.pho_server import _pick_device
from faster_whisper import WhisperModel
from backend.services.stt_service import moi_tu_vung
dev,ct=_pick_device()
stt=WhisperModel(r"C:\duan\chat-ai\models\phowhisper\PhoWhisper-medium-ct2",device=dev,compute_type=ct)
MOI=moi_tu_vung("nam")
BO=[("vay tín chấp",["lãi suất vay tín chấp bao nhiêu","vay được tối đa bao nhiêu","cần giấy tờ gì"]),
    ("vay mua nhà",["anh muốn vay mua nhà","lãi suất thế nào","thời hạn tối đa mấy năm"]),
    ("thẻ tín dụng",["hạn mức bao nhiêu","miễn lãi bao nhiêu ngày","phí thường niên thế nào"]),
    ("tiết kiệm",["lãi suất gửi tiết kiệm bao nhiêu","kỳ hạn nào lợi nhất","rút trước hạn sao"])]
def nghe(w):
    s,_=stt.transcribe(io.BytesIO(w),language="vi",initial_prompt=MOI,
                       vad_filter=False,beam_size=5,word_timestamps=True)
    return [x for g in s for x in (g.words or []) if x.end>x.start]
def sach(s): return unicodedata.normalize("NFC",s.strip().lower().strip(".,?!:;"))
async def main():
    lech=[]; nhanh=Counter(); dodai=[]
    for sp,qs in BO:
        async with websockets.connect("ws://127.0.0.1:8100/ws/call/new",max_size=None) as ws:
            await ws.recv()
            await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh","product":sp}))
            while True:
                if json.loads(await ws.recv()).get("type")=="session_updated": break
            for i,q in enumerate(qs,1):
                await ws.send(json.dumps({"type":"text","text":q,"turn_id":i}))
                goi=[]; tra=""
                while True:
                    m=json.loads(await asyncio.wait_for(ws.recv(),timeout=240))
                    if m.get("type")=="audio" and not m.get("is_filler") and m.get("data"):
                        goi.append((m.get("chunk_id",0),base64.b64decode(m["data"])))
                    if m.get("type")=="turn_complete": tra=m.get("full_response",""); break
                goi.sort(key=lambda x:x[0])
                manh=_cat_manh_nhu_pipeline(tra)
                for j,(_,w) in enumerate(goi):
                    if j>=len(manh): break
                    wl=nghe(w)
                    if not wl: continue
                    mong=[t for t in re.sub(r"[^\w\s]"," ",normalize_for_tts(manh[j])).split()]
                    if not mong: continue
                    with wave.open(io.BytesIO(w)) as r: giay=r.getnframes()/r.getframerate()
                    if sach(wl[-1].word)!=sach(mong[-1]):
                        lech.append((manh[j][-42:], " ".join(x.word for x in wl[-4:]),
                                     giay-wl[-1].end))
                    for x in wl:
                        d=x.end-x.start
                        if 60.0/d>800: nhanh[sach(x.word)]+=1; dodai.append(d)
    print(f"\n=== ÂM TIẾT CUỐI LỆCH: {len(lech)} chỗ ===")
    for a,b,d in lech[:14]:
        print(f"  chữ  ...{a}\n  nghe ...{b}   | còn {d*1000:.0f}ms tiếng sau chữ cuối")
    print(f"\n=== CHỮ >800 â.t/phút: {sum(nhanh.values())} lượt xuất hiện ===")
    print(" ",dict(nhanh.most_common(14)))
    if dodai: print(f"  độ dài các chữ đó: {min(dodai)*1000:.0f}-{max(dodai)*1000:.0f}ms "
                    f"(mốc đo của Whisper là bội của 20ms)")
asyncio.run(main())
