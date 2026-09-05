"""Chay NHIEU VONG cho loi bia tien tai xuat hien, xem luoi chan co no that khong.

Vi sao can: ban sua luoi chan tien (commit 5c0f9a7) moi chi chung minh o tang
ham. Chay end-to-end 4 lan sau khi sua thi LLM khong lap lai loi bia lan nao,
nen nhanh "ngu canh rong so" chua co dip no tren duong that.

Loi bia phu thuoc LLM nen khong goi ra theo y muon duoc - chi con cach chay
nhieu vong va dem.

Ba nhom cau, chon de DE kich hai nhanh cua luoi:

  A. tai hien  - dung 7 luot may nghe duoc trong cuoc goi that 4cd44fb7, cung
                 mot phien de co lich su dan dat y nhu that
  B. khong co tai lieu - hoi SO TIEN ve tiet kiem / bao hiem. `knowledge/` khong
                 co tai lieu nao cho hai san pham nay, nen ngu canh se rong ->
                 dung dieu kien cua nhanh A trong luoi (bia tu tri nho model)
  C. han muc mo ho - hoi han muc kieu de LLM tu suy so, nham nhanh B (lay so
                 cua MUC KHAC, vd so trong vi du tra gop)

Chay:  .venv\\python.exe scripts\\do_luoi_nhieu_vong.py [so_vong]
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import websockets

DU_AN = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")

URL_GOC = "ws://127.0.0.1:8100/ws/call"
PHIEN = int(time.time())
SO_VONG = int(sys.argv[1]) if len(sys.argv) > 1 else 8

NHOM = {
    # dung chu may nghe duoc LUC GOI THAT, lay tu app.db
    "A_tai_hien": ["cũng như nào", "như nào", "đúng rồi", "lãi suất rất nhiều",
                   "đại sơn văn tín trăm ba nhiều", "mừng được mời nhiều",
                   "sẵn mức được bao nhiêu"],
    "B_khong_tai_lieu": ["gửi tiết kiệm tối thiểu bao nhiêu tiền",
                         "bảo hiểm nhân thọ đóng bao nhiêu một năm",
                         "sổ tiết kiệm mở tối thiểu bao nhiêu",
                         "gói bảo hiểm rẻ nhất giá bao nhiêu"],
    "C_han_muc_mo_ho": ["vay được nhiều nhất bao nhiêu",
                        "hạn mức của em được bao nhiêu",
                        "người thu nhập 10 triệu vay được mấy trăm",
                        "hạn mức thấp nhất và cao nhất là bao nhiêu"],
}

# So tien trong cau tra loi (de dem "AI co neu so tien khong")
_TIEN = re.compile(r"\d[\d.,]*\s*(?:triệu|tỷ|tỉ|nghìn|đồng)"
                   r"|(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|trăm)"
                   r"[\w\s]{0,20}?\s*(?:triệu|tỷ|tỉ)", re.I)


async def mot_vong(nhom: str, cau_list: list[str], v: int) -> dict:
    """Mot phien, gui het cac cau trong nhom. Tra thong ke cua vong do."""
    ket = {"neu_tien": 0, "chan": [], "dap": [], "lot": []}
    url = f"{URL_GOC}/luoi_{nhom}_{PHIEN}_{v}"
    async with websockets.connect(url, max_size=None) as ws:
        await ws.recv()
        for cau in cau_list:
            await ws.send(json.dumps({"type": "text", "text": cau}))
            while True:
                try:
                    tin = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
                except asyncio.TimeoutError:
                    break
                if tin.get("type") != "turn_complete":
                    continue
                dap = (tin.get("full_response") or "").strip()
                sd = tin.get("metrics", {}) or {}
                co_chan = any(sd.get(t) for t in
                              ("chan_tien_sai", "chan_so_sai", "chan_lai_suat_bia"))
                if _TIEN.search(dap):
                    ket["neu_tien"] += 1
                    if not co_chan:
                        # Cau NEU SO TIEN ma luoi KHONG chan - day moi la ca lot
                        ket["lot"].append(
                            f"[{nhom} v{v}] khach: {cau!r}\n      AI: {dap[:110]!r}")
                for ten in ("chan_tien_sai", "chan_so_sai", "chan_lai_suat_bia"):
                    if sd.get(ten):
                        ket["chan"].append(f"[{nhom} v{v}] {ten}: {sd[ten]}\n"
                                           f"      khach: {cau!r}\n      AI   : {dap[:90]!r}")
                ket["dap"].append((cau, dap))
                break
    return ket


async def main():
    tong = {n: {"luot": 0, "neu_tien": 0, "chan": [], "lot": []} for n in NHOM}
    t0 = time.perf_counter()
    for v in range(1, SO_VONG + 1):
        for nhom, cau_list in NHOM.items():
            r = await mot_vong(nhom, cau_list, v)
            tong[nhom]["luot"] += len(cau_list)
            tong[nhom]["neu_tien"] += r["neu_tien"]
            tong[nhom]["chan"] += r["chan"]
            tong[nhom]["lot"] += r["lot"]
        xong = sum(t["luot"] for t in tong.values())
        print(f"vong {v}/{SO_VONG} xong ({xong} luot, "
              f"{sum(len(t['chan']) for t in tong.values())} lan luoi no)", flush=True)

    dong = [f"CHAY {SO_VONG} VONG - {time.perf_counter()-t0:.0f}s\n"]
    for nhom, t in tong.items():
        dong.append(f"\n{'='*70}\n{nhom}: {t['luot']} luot | "
                    f"{t['neu_tien']} luot co neu so tien | "
                    f"{len(t['chan'])} lan luoi no")
        dong += ["  " + c for c in t["chan"]]
        if t["lot"]:
            dong.append(f"  --- {len(t['lot'])} CA LOT (neu so tien ma khong bi chan) ---")
            dong += ["  " + c for c in t["lot"]]
    ra = DU_AN / "data" / "ket_luoi_nhieu_vong.txt"
    ra.write_text("\n".join(dong), encoding="utf-8")
    print("\n".join(dong[-40:]))
    print(f"\n-> {ra}")

asyncio.run(main())
