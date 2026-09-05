"""Đo tỉ lệ GỘP MẢNH trên lượt thật qua WebSocket, với câu hỏi ép trả lời DÀI (>=3 mảnh)."""
import asyncio, json, sys, time, uuid
import websockets
sys.stdout.reconfigure(encoding="utf-8")
WS = "ws://127.0.0.1:8100/ws/call/"
CAU = [
    "Em giới thiệu chi tiết giúp anh gói vay mua nhà: lãi suất, thời hạn, hạn mức và cần giấy tờ gì?",
    "Anh muốn biết đầy đủ các bước làm hồ sơ vay tín chấp từ đầu đến lúc nhận tiền, em nói kỹ giúp anh.",
    "Em so sánh giúp chị gói tiết kiệm sáu tháng với mười hai tháng, lãi bao nhiêu, rút trước hạn thì sao?",
    "Thẻ tín dụng bên em có phí gì, miễn lãi bao lâu, hạn mức thế nào và làm mất thẻ thì xử lý ra sao?",
]
async def luot(cau):
    sid = str(uuid.uuid4())
    async with websockets.connect(WS + sid, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "text", "text": cau}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=90)
            m = json.loads(raw) if isinstance(raw, str) else None
            if m and m.get("type") == "turn_complete":
                return m.get("metrics", {})
async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    await luot(CAU[0])  # khởi động
    tong_noi = tong_gop = 0
    for v in range(n):
        for c in CAU:
            mt = await luot(c)
            g = mt.get("gop_manh", "-")
            print(f"[{v}] gop {g:>5}  ttfa {mt.get('ttfa_ms')}ms  {c[:40]}")
            if isinstance(g, str) and "/" in g:
                a, b = g.split("/"); tong_gop += int(a); tong_noi += int(b)
    print(f"TỔNG: gộp {tong_gop}/{tong_noi} chỗ nối = {100*tong_gop/max(tong_noi,1):.0f}%")
asyncio.run(main())
