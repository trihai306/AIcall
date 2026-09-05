import asyncio, json, sys, time, uuid
import websockets
sys.stdout.reconfigure(encoding="utf-8")
WS = "ws://127.0.0.1:8100/ws/call/"
async def luot(ws, cau):
    t0 = time.perf_counter(); ttfa = None
    await ws.send(json.dumps({"type": "text", "text": cau}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=90)
        m = json.loads(raw) if isinstance(raw, str) else None
        if m and m.get("type") == "audio" and ttfa is None and not m.get("is_filler"):
            ttfa = (time.perf_counter() - t0) * 1000
        if m and m.get("type") == "turn_complete":
            mt = m.get("metrics", {})
            print(f"{cau[:28]:28s} | tieng_san={mt.get('tieng_san','-'):16s} ttfa={mt.get('ttfa_ms')}ms "
                  f"tts_first={mt.get('tts_first_ms')}ms bang={mt.get('bang_hoi_dap','-')} "
                  f"doc_thang={mt.get('bang_doc_thang','-')} ltg={mt.get('luot_thuong_gap','-')} chunks={mt.get('tts_chunks')}")
            return mt
async def main():
    for c in ["alo ai đấy", "cần những giấy tờ gì", "vay như nào", "alo ai đấy", "cần chuẩn bị gì"]:
        async with websockets.connect(WS + str(uuid.uuid4()), max_size=None) as ws:
            await ws.recv()
            await luot(ws, c)
        await asyncio.sleep(3)
asyncio.run(main())
