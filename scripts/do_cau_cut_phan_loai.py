"""Cau CUT co phan loai duoc tinh huong khong?

Vi sao hoi: `_send_filler` cho toi da `_CHO_TINH_HUONG_MS = 150ms` de
`speculate(ngay=True)` phien am TRON cau, nhung STT mat 200-500ms nen thuong
het han -> `session.tinh_huong` van rong -> cau dem roi ve ro chung. Do duoc
tren duong that: cho 113-162ms roi van None, ca 7/7 luot.

Neu cau CUT (ban phien am giua chung, co san som hon) van phan loai duoc thi
khong can cho ban tron - do la duong ra ma khong phai tra gia bang do tre.

Chay:  .venv\\python.exe scripts\\do_cau_cut_phan_loai.py
"""
import json
import sqlite3
import sys
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.filler_situation import (NGUONG_DIEM, chon_tinh_huong,  # noqa: E402
                                               chuan_hoa)
from backend.services.rag_service import RAGService  # noqa: E402

TY_LE = [1.0, 0.8, 0.6, 0.5, 0.4]


def main():
    seed = json.loads((DU_AN / "data" / "tinh_huong_seed.json").read_text("utf-8"))
    ds = seed["tinh_huong"] if isinstance(seed, dict) else seed
    rag = RAGService(); rag.load()
    kho = {t["id"]: chuan_hoa(rag.embed(t["vi_du"])) for t in ds if t.get("vi_du")}

    cn = sqlite3.connect(str(DU_AN / "data" / "app.db"))
    luot = [r[0] for r in cn.execute(
        "SELECT content FROM conversation_turns WHERE role='user'")]
    cn.close()
    # chi giu luot STT du dai de cat duoc
    cau = [t for t in luot if t and t[0].islower() and len(t.split()) >= 4][:300]
    print(f"{len(cau)} cau khach that | NGUONG = {NGUONG_DIEM}\n")

    # nhan = tinh huong khop tren cau TRON (coi la dung)
    nhan = {}
    for t in cau:
        id_th, _ = chon_tinh_huong(chuan_hoa(rag.embed([t]))[0], kho)
        nhan[t] = id_th

    print(f"{'giu':>6} {'khop':>6} {'dung nhu cau tron':>18}")
    print("-" * 36)
    for ty in TY_LE:
        khop = dung = 0
        for t in cau:
            tu = t.split()
            cut = " ".join(tu[:max(1, int(len(tu) * ty))])
            if len(cut) < 4:
                continue
            id_th, _ = chon_tinh_huong(chuan_hoa(rag.embed([cut]))[0], kho)
            if id_th:
                khop += 1
                if id_th == nhan[t]:
                    dung += 1
        print(f"{ty*100:>5.0f}% {khop:>6} {dung:>18}"
              f"   ({dung/max(khop,1)*100:.0f}% khop dung)")

main()
