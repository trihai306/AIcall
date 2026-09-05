"""Tai hien cuoc goi 4cd44fb7 o TANG CHU: gui dung 7 luot ma may nghe duoc
luc goi that, trong CUNG MOT PHIEN de co lich su dan dat y nhu that.

Muc dich: tao lai dieu kien da lam AI bia "200 - ba tram trieu", roi xem luoi
chan tien co no khong. Chay N vong vi loi bia co yeu to ngau nhien cua LLM.
"""
import asyncio
import json, sys, io
from pathlib import Path
import websockets

DU_AN = Path(__file__).resolve().parents[1]

# Chu may nghe duoc LUC GOI THAT, lay tu app.db (conversation_turns)
LUOT = ["cũng như nào", "như nào", "đúng rồi", "lãi suất rất nhiều",
        "đại sơn văn tín trăm ba nhiều", "mừng được mời nhiều",
        "sẵn mức được bao nhiêu"]
SO_VONG = 3

async def mot_vong(v):
    url = f"ws://127.0.0.1:8100/ws/call/tai_hien_goc_{v}"
    ra = [f"\n{'#'*70}\nVONG {v}"]
    co_chan, co_bia = 0, []
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()
        for i, cau in enumerate(LUOT, 1):
            await ws.send(json.dumps({"type": "text", "text": cau}))
            while True:
                try:
                    tin = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
                except asyncio.TimeoutError:
                    ra.append(f"  luot {i}: (qua han)"); break
                if tin.get("type") == "turn_complete":
                    dap = (tin.get("full_response") or "").strip()
                    sd = tin.get("metrics", {}) or {}
                    chan = {k: v for k, v in sd.items() if "chan" in k}
                    if chan: co_chan += 1
                    # so tien SAI thuong gap: 200/300 trieu cho han muc
                    if ("trăm triệu" in dap or "200 triệu" in dap) and "năm trăm" not in dap:
                        co_bia.append(f"luot {i}: {dap[:70]}")
                    ra.append(f"  luot {i} [{cau}]\n     dap : {dap[:95]}"
                              + (f"\n     LUOI: {chan}" if chan else ""))
                    break
    ra.append(f"  --> vong {v}: {co_chan} lan luoi no | nghi bia: {co_bia or 'khong'}")
    return "\n".join(ra)

async def main():
    ra = []
    for v in range(1, SO_VONG + 1):
        ra.append(await mot_vong(v)); print(f"vong {v} xong")
    io.open(DU_AN / "data" / "ket_tai_hien.txt","w",encoding="utf-8").write("\n".join(ra))
asyncio.run(main())
