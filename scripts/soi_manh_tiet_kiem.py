"""Luoi chan nhan duoc DUNG manh nao? Thu response_chunk."""
import asyncio, json, sys
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
from backend.pipeline.text_normalizer import chan_lai_suat_bia
WS="ws://127.0.0.1:8100/ws/call/new"
async def hoi(sp,q):
    async with websockets.connect(WS,max_size=None,open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh","product":sp}))
        while True:
            if json.loads(await ws.recv()).get("type")=="session_updated": break
        await ws.send(json.dumps({"type":"text_soi","text":q,"turn_id":1}))
        manh=[]
        while True:
            m=json.loads(await asyncio.wait_for(ws.recv(),timeout=180))
            if m.get("type")=="response_chunk":
                manh.append(m.get("text") or m.get("chunk") or "")
            if m.get("type")=="turn_complete":
                return manh, m.get("full_response",""), (m.get("metrics") or {})
async def main():
    for lan in range(1,4):
        manh,tra,mt=await hoi("tiết kiệm","lãi suất gửi tiết kiệm bao nhiêu")
        print(f"\n--- lần {lan}: {len(manh)} mảnh · lưới "
              f"{mt.get('chan_lai_suat_bia') or '(không nổ)'}")
        for i,x in enumerate(manh,1):
            ra,sua=chan_lai_suat_bia(x,"")
            print(f"   {i}. {x[:70]!r}"+(f"   <- lưới BẮT: {sua}" if sua else ""))
        print(f"   trả lời cuối: {tra[:80]!r}")
asyncio.run(main())
