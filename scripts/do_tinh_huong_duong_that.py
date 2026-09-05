"""Vi sao duong that chi 2,5% co tinh huong, trong khi phan loai lam duoc 59%?

Ba nghi pham:
  A. phan loai kem   -> DA LOAI: `do_phan_loai_tinh_huong.py` cho 59,3% khop
  B. chua KIP        -> `spec_stt` chua co luc `_send_filler` doc no
  C. DO PHU thap     -> phan loai dung nhung bi bo vi `n_th/n_audio < 0.5`

Script nay day 7 luot TIENG THAT qua WebSocket cua backend dang chay va in cac
so do lien quan: `tinh_huong_cho_ms`, `tinh_huong_do_phu`, `tinh_huong_diem`,
`tinh_huong_bo`, `tinh_huong_id`, `filler_text`.

Chay:  .venv\\python.exe scripts\\do_tinh_huong_duong_that.py
"""
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

import websockets

DU_AN = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

VAO = DU_AN / "data" / "luot_that"
PHIEN = int(time.time())


async def main():
    files = sorted(VAO.glob("luot_*.raw"))
    if not files:
        print("chua co tieng - chay lai buoc trich"); return
    url = f"ws://127.0.0.1:8100/ws/call/do_tinh_huong_{PHIEN}"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()
        for f in files:
            # Gui theo LUONG nhu duong that: audio_chunk nhieu manh roi audio_end.
            # Gui mot cuc ({"type":"audio"}) thi KHONG kich `speculate()`, nen
            # `spec_stt` rong va `session.tinh_huong` luon None - do mot duong
            # khong ton tai trong cuoc goi that. Day la bay da mac o ban dau.
            pcm = f.read_bytes()
            BUOC = 3200          # 100ms @ 16kHz 16-bit
            for i in range(0, len(pcm), BUOC):
                await ws.send(json.dumps({
                    "type": "audio_chunk",
                    "data": base64.b64encode(pcm[i:i+BUOC]).decode()}))
                # NHIP THAT: 3200 byte = 100ms tieng @16kHz, nen phai ngu dung
                # 100ms. Ngu 20ms la cho "khach noi" nhanh gap 5 lan doi that,
                # `speculate()` khong kip chay lan nao va `spec_stt` rong -> do ra
                # ket luan sai rang `_CHO_TINH_HUONG_MS` qua ngan.
                await asyncio.sleep(0.1)
            await ws.send(json.dumps({"type": "audio_end"}))
            pa = ""
            while True:
                t = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
                if t.get("type") == "transcript":
                    pa = t.get("text", "")
                elif t.get("type") == "turn_complete":
                    m = t.get("metrics", {}) or {}
                    print(f"\n{f.name}  nghe: {pa!r}")
                    print(f"   cho tinh huong : {m.get('tinh_huong_cho_ms','-')} ms")
                    print(f"   do phu         : {m.get('tinh_huong_do_phu','-')}"
                          f"   (can >= 0.5)")
                    print(f"   diem           : {m.get('tinh_huong_diem','-')}"
                          f"   (can >= 0.75)")
                    print(f"   bo vi          : {m.get('tinh_huong_bo','(khong bo)')}")
                    print(f"   tinh huong DUNG: {m.get('tinh_huong_id','(ro chung)')}")
                    print(f"   cau dem        : {m.get('filler_text','-')!r}")
                    print(f"   [soi] spec_stt : {m.get('_soi_spec_stt','-')!r}")
                    print(f"   [soi] tinh_huong: {m.get('_soi_tinh_huong','-')}")
                    print(f"   [soi] spec_task: {m.get('_soi_spec_task','-')}")
                    if m.get("filler_bo_qua"):
                        print(f"   BO CAU DEM     : {m['filler_bo_qua']}")
                    break

asyncio.run(main())
