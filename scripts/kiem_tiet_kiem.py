"""Hoi ve san pham KHONG co tai lieu - AI co con muon so cua san pham khac khong."""
import asyncio, json, re, sys
sys.path.insert(0, r"C:\duan\chat-ai"); sys.stdout.reconfigure(encoding="utf-8")
import websockets
WS="ws://127.0.0.1:8100/ws/call/new"
CA=[("tiết kiệm","lãi suất gửi tiết kiệm bao nhiêu"),
    ("tiết kiệm","gửi 100 triệu kỳ hạn 12 tháng được bao nhiêu lãi"),
    ("bảo hiểm","phí bảo hiểm nhân thọ thế nào"),
    # doi chung: san pham CO tai lieu phai tra loi binh thuong
    ("vay tín chấp","lãi suất vay tín chấp bao nhiêu"),
    ("thẻ tín dụng","hạn mức thẻ tín dụng bao nhiêu")]
async def hoi(sp,q):
    async with websockets.connect(WS,max_size=None,open_timeout=30) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type":"set_session","customer_name":"Anh Minh","product":sp}))
        while True:
            if json.loads(await ws.recv()).get("type")=="session_updated": break
        await ws.send(json.dumps({"type":"text_soi","text":q,"turn_id":1}))
        while True:
            m=json.loads(await asyncio.wait_for(ws.recv(),timeout=180))
            if m.get("type")=="turn_complete":
                return m.get("full_response",""), m.get("metrics",{}) or {}
async def main():
    print(f"{'sản phẩm':<14}{'có tài liệu':>12}   câu trả lời")
    print("-"*100)
    for sp,q in CA:
        tra,mt=await hoi(sp,q)
        ng=[n for n in (mt.get("rag_nguon") or []) if not n.get("bi_loc")]
        sp_ng=[n["nguon"] for n in ng if n.get("nguon","").replace(".md","") in
               ("vay_tin_chap","vay_mua_nha","the_tin_dung")]
        so=re.findall(r"\d+[.,]?\d*\s*%", tra)
        print(f"{sp:<14}{'có' if sp_ng else 'KHÔNG':>12}   {tra[:72]}")
        chan={k:v for k,v in mt.items() if "chan" in k}
        print(f"{'':26}   nguồn giữ lại: {[n['nguon'] for n in ng] or '(không)'}"
              + (f"   ⚠ CÓ SỐ %: {so}" if so else "")
              + (f"   lưới chặn: {chan}" if chan else "   lưới chặn: (không nổ)"))
asyncio.run(main())
