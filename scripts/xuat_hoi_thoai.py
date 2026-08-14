"""Xuat tieng cua 10 hoi thoai ra Desktop de nghe.

Moi hoi thoai mot thu muc: tung luot mot file WAV (da NOI cac manh, dung nhip
nghi that cua duong goi) + Loi.txt ghi khach hoi gi, may tra gi.
"""
import asyncio, base64, io, json, sys, wave
from pathlib import Path
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
from backend.api.voices import _cat_manh_nhu_pipeline
import ast
def _doc_hoi_thoai():
    cay=ast.parse(Path(r"C:\duan\chat-ai\scripts\test_100_luot.py").read_text(encoding="utf-8"))
    for n in cay.body:
        if isinstance(n,ast.Assign) and getattr(n.targets[0],"id","")=="HOI_THOAI":
            return ast.literal_eval(n.value)
    raise SystemExit("khong thay HOI_THOAI")
HOI_THOAI=_doc_hoi_thoai()
GOC=Path.home()/"Desktop"/"Check giọng"/"Hoi thoai 100 luot"
async def main():
    GOC.mkdir(parents=True,exist_ok=True)
    for k,(sp,qs) in enumerate(HOI_THOAI[:10],1):
        tm=GOC/f"{k:02d} - {sp}"; tm.mkdir(exist_ok=True); loi=[]
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
                pcm=[]
                for j,(_,w) in enumerate(goi):
                    with wave.open(io.BytesIO(w)) as r: pcm.append(r.readframes(r.getnframes()))
                with wave.open(str(tm/f"luot {i}.wav"),"wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
                    w.writeframes(b"".join(pcm))
                loi.append(f"--- Lượt {i} ---\nKhách : {q}\nMáy   : {tra}\n"
                           f"(cắt thành {len(_cat_manh_nhu_pipeline(tra))} mảnh)\n")
        (tm/"Lời.txt").write_text("\n".join(loi),encoding="utf-8")
        print(f"  {k:02d}/10 {sp} xong",flush=True)
    print(f"\nĐã ghi vào: {GOC}")
asyncio.run(main())
