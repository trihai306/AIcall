"""Phien am tren doan DAU NGAN co ra chu du de phan loai tinh huong khong?

Vi sao hoi: `_SPEC_MIN_MS = 600` nen `speculate()` chi bat dau sau 600ms tieng,
roi STT mat them 200-500ms. Do tren duong that (nhip 100ms/chunk dung thuc te):
luot 1,75s thi KIP phan loai (hoi_han_muc, diem 0,804), con luot 0,9-1,3s thi
khong - ma phan lon luot khach that nam trong khoang 0,9-1,3s.

Chu thich cua hang ghi "ngan hon thi phien am chua ra gi". Day la phep do kiem
lai chinh cau do, trong tieng khach THAT.

Chay:  .venv\\python.exe scripts\\do_doan_som.py
"""
import asyncio
import json
import sys
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.filler_situation import (NGUONG_DIEM, chon_tinh_huong,  # noqa: E402
                                               chuan_hoa)
from backend.services.rag_service import RAGService  # noqa: E402
from backend.services.stt_service import STTService  # noqa: E402

VAO = DU_AN / "data" / "luot_that"
MOC_MS = [300, 400, 500, 600, 800, 1000]
SR = 16000


async def main():
    seed = json.loads((DU_AN / "data" / "tinh_huong_seed.json").read_text("utf-8"))
    ds = seed["tinh_huong"] if isinstance(seed, dict) else seed
    rag = RAGService(); rag.load()
    kho = {t["id"]: chuan_hoa(rag.embed(t["vi_du"])) for t in ds if t.get("vi_du")}
    stt = STTService()

    files = sorted(VAO.glob("luot_*.raw"))
    print(f"{len(files)} luot | NGUONG_DIEM = {NGUONG_DIEM}\n")

    # nhan = tinh huong tren cau TRON
    nhan = {}
    for f in files:
        chu = (await stt.transcribe(f.read_bytes(), sample_rate=SR)).strip()
        id_th, diem = (chon_tinh_huong(chuan_hoa(rag.embed([chu]))[0], kho)
                       if len(chu) >= 4 else (None, 0.0))
        nhan[f.name] = (chu, id_th)
        print(f"{f.name} ({len(f.read_bytes())/2/SR:.2f}s) tron: {chu!r} -> {id_th}")

    print(f"\n{'moc':>6} {'ra chu':>7} {'phan loai':>10} {'dung nhu tron':>14}")
    print("-" * 42)
    for ms in MOC_MS:
        n_byte = int(SR * ms / 1000) * 2
        co_chu = khop = dung = 0
        for f in files:
            pcm = f.read_bytes()[:n_byte]
            if len(pcm) < 320:
                continue
            chu = (await stt.transcribe(pcm, sample_rate=SR)).strip()
            if len(chu) >= 4:
                co_chu += 1
                id_th, _ = chon_tinh_huong(chuan_hoa(rag.embed([chu]))[0], kho)
                if id_th:
                    khop += 1
                    if id_th == nhan[f.name][1]:
                        dung += 1
        print(f"{ms:>4}ms {co_chu:>7} {khop:>10} {dung:>14}")
    await stt.close()

asyncio.run(main())
