"""Vi sao 97% luot KHONG phan loai duoc tinh huong cho cau dem?

Do tren `latency_metrics`: chi 2/80 luot cuoc goi CO GHI AM co `tinh_huong_id`
(2,5%), tuc co che "chon cau dem theo ngu canh" gan nhu khong bao gio chay va
moi thu roi ve ro chung.

Ba nghi pham, phai tach ra:
  A. Phan loai KEM  - chay tren cau khach that ma diem duoi nguong
  B. Chua KIP       - `spec_stt` chua co luc `_send_filler` doc
  C. DO PHU thap    - phan loai dung nhung bi bo vi doan nghe qua ngan

Script nay do NGHI PHAM A: chay thang `chon_tinh_huong` tren cac cau khach that
lay tu app.db, khong qua timing. Ra tot => loi o B/C, ra kem => loi o A.

Chay:  .venv\\python.exe scripts\\do_phan_loai_tinh_huong.py
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.filler_situation import (NGUONG_DIEM, chon_tinh_huong,  # noqa: E402
                                               chuan_hoa)
from backend.services.rag_service import RAGService  # noqa: E402


def main():
    seed = json.loads((DU_AN / "data" / "tinh_huong_seed.json").read_text("utf-8"))
    ds = seed["tinh_huong"] if isinstance(seed, dict) else seed
    print(f"kho: {len(ds)} tinh huong | NGUONG_DIEM = {NGUONG_DIEM}")

    rag = RAGService(); rag.load()
    kho = {}
    for th in ds:
        vd = th.get("vi_du") or []
        if vd:
            kho[th["id"]] = chuan_hoa(rag.embed(vd))

    cn = sqlite3.connect(str(DU_AN / "data" / "app.db"))
    luot = [r[0] for r in cn.execute(
        "SELECT content FROM conversation_turns WHERE role='user'")]
    cn.close()
    stt = [t for t in luot if t and t[0].islower() and len(t) >= 4]
    print(f"{len(stt)} luot khach do STT sinh\n")

    trung, truot, diem_truot = 0, 0, []
    dem_th = Counter()
    vd_truot = []
    for t in stt:
        q = chuan_hoa(rag.embed([t]))[0]
        id_th, diem = chon_tinh_huong(q, kho)
        if id_th:
            trung += 1; dem_th[id_th] += 1
        else:
            truot += 1; diem_truot.append(diem)
            if len(vd_truot) < 12:
                vd_truot.append((round(diem, 3), t[:56]))

    print(f"KHOP   : {trung}/{len(stt)} ({trung/len(stt)*100:.1f}%)")
    print(f"TRUOT  : {truot}/{len(stt)} ({truot/len(stt)*100:.1f}%)")
    if diem_truot:
        diem_truot.sort()
        n = len(diem_truot)
        print(f"  diem cua cac luot truot: min {diem_truot[0]:.3f} | "
              f"trung vi {diem_truot[n//2]:.3f} | max {diem_truot[-1]:.3f}")
        gan = sum(1 for d in diem_truot if d >= NGUONG_DIEM - 0.08)
        print(f"  trong do {gan} luot chi thieu < 0.08 diem la khop")
    print("\n=== tinh huong khop nhieu nhat ===")
    for k, v in dem_th.most_common(8):
        print(f"  {v:>4}  {k}")
    print("\n=== vi du luot TRUOT (diem, cau) ===")
    for d, t in vd_truot:
        print(f"  {d:.3f}  {t!r}")

main()
