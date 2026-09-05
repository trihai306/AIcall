"""Kiem chung END-TO-END luoi chan tien, bang duong CHU (bo qua STT).

Gui DUNG cau rac ma may nghe duoc trong cuoc goi that o luot 6. Cau nay keo
RAG di lac -> ngu canh rong so -> truoc khi sua thi so bia lot thang ra loa.

Moi cau chay trong 1 PHIEN RIENG de khong co luot truoc dan duong.
"""
import asyncio
import json, sys, io
from pathlib import Path
import websockets

DU_AN = Path(__file__).resolve().parents[1]

CAU = [
    "hắn mừng được mời nhiều",        # dung chu may nghe duoc luot 6 (lan chay dau)
    "mừng được mời nhiều",            # chu may nghe LUC GOI THAT
    "đại sơn văn tín trăm ba nhiều",  # chu may nghe LUC GOI THAT (luot 5)
    "hạn mức được bao nhiêu",         # cau DUNG - doi chung, khong duoc chan
]

async def mot_phien(i, cau):
    url = f"ws://127.0.0.1:8100/ws/call/kiem_luoi_{i}"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "text", "text": cau}))
        dap, so_do = "", {}
        while True:
            try:
                tin = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
            except asyncio.TimeoutError:
                return "(qua han)", {}
            if tin.get("type") == "turn_complete":
                return tin.get("full_response", ""), tin.get("metrics", {}) or {}

async def main():
    ra = []
    for i, cau in enumerate(CAU, 1):
        dap, sd = await mot_phien(i, cau)
        chan = sd.get("chan_tien_sai") or sd.get("chan_so_sai") or sd.get("chan_lai_suat_bia")
        ra.append(f"\n{'='*70}\nkhach (chu): {cau!r}")
        ra.append(f"  AI dap : {dap.strip()}")
        ra.append(f"  luoi   : {chan if chan else '(khong chan)'}")
        ra.append(f"  metrics: {  {k:v for k,v in sd.items() if 'chan' in k} }")
        print(f"cau {i} xong")
    io.open(DU_AN / "data" / "ket_kiem_luoi.txt","w",encoding="utf-8").write("\n".join(ra))
asyncio.run(main())
