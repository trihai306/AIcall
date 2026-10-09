"""Chạy một BỘ HỘI THOẠI THỬ qua đường trả lời thật rồi ghi lại AI đáp gì.

Mỗi hội thoại là một phiên WebSocket riêng (như một cuộc gọi), các lượt gửi lần
lượt bằng tin `text_soi` - cùng đường nghiệp vụ với cuộc gọi nhưng không sinh
tiếng, nên vài trăm lượt chạy trong vài phút và không chiếm GPU của TTS.

    .venv\\python.exe scripts\\chay_bo_thu_tra_loi.py data\\bo_thu\\vao.json data\\bo_thu\\ra.json

Tệp vào: danh sách `{"ma", "san_pham", "luot": [lời khách...]}`. Tệp ra giữ
nguyên mọi trường và thêm `ket_qua`: mỗi lượt một `{khach, ai, duong, ly_do,
ttfa_ms}` - `duong` là đường đã trả lời (rule / answer_bank / kho_khong_co /
generated...).

Chạy từ thư mục gốc dự án, backend phải đang lên ở cổng 8100.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import websockets

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

WS = "ws://127.0.0.1:8100/ws/call/"


async def mot_hoi_thoai(hd: dict, stt: int) -> list[dict]:
    ra: list[dict] = []
    async with websockets.connect(f"{WS}bo_thu_{int(time.time() * 1000)}_{stt}",
                                  max_size=None) as ws:
        await ws.send(json.dumps({"type": "set_session", "customer_name": "Anh/Chị",
                                  "product": hd.get("san_pham", "")}))
        while json.loads(await ws.recv()).get("type") != "session_updated":
            pass
        for i, cau in enumerate(hd.get("luot", []), 1):
            await ws.send(json.dumps({"type": "text_soi", "text": cau, "turn_id": i}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), 180)
                if isinstance(raw, bytes):
                    continue
                m = json.loads(raw)
                if m.get("type") == "turn_complete":
                    break
            me = m.get("metrics", {}) or {}
            r = me.get("answer_route", {}) or {}
            ra.append({"khach": cau, "ai": m.get("full_response", ""),
                       "duong": r.get("mode") or "", "ly_do": r.get("reason") or "",
                       "ttfa_ms": me.get("ttfa_ms")})
    return ra


async def main() -> int:
    vao, ra = Path(sys.argv[1]), Path(sys.argv[2])
    bo = json.loads(vao.read_text(encoding="utf-8"))
    t0 = time.time()
    for stt, hd in enumerate(bo):
        try:
            hd["ket_qua"] = await mot_hoi_thoai(hd, stt)
        except Exception as e:  # một hội thoại hỏng không được làm mất cả bộ
            hd["ket_qua"] = []
            hd["loi"] = repr(e)[:200]
        if stt % 10 == 9:
            print(f"  {stt + 1}/{len(bo)} hội thoại, {time.time() - t0:.0f}s", flush=True)
    ra.parent.mkdir(parents=True, exist_ok=True)
    ra.write_text(json.dumps(bo, ensure_ascii=False, indent=1), encoding="utf-8")
    luot = [k for hd in bo for k in hd.get("ket_qua", [])]
    dem: dict[str, int] = {}
    for k in luot:
        dem[k["duong"] or "?"] = dem.get(k["duong"] or "?", 0) + 1
    print(f"xong {len(bo)} hội thoại, {len(luot)} lượt, {time.time() - t0:.0f}s")
    print("theo đường:", dict(sorted(dem.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
