"""Siet NGUONG_DIEM co lam cau dem chon CHUAN hon khong?

Do 05-09-2026 tren 102 luot tieng khach that: noi luoi loc KHONG giup (ban tho
ngang hoac kem ban loc). Nhung so do lo ra van de lon hon: ngay ca khi phan loai
duoc, chi ~50-60% la DUNG.

    moc 1000ms: chon 29, dung 15   -> 14 luot chon SAI tinh huong
    moc 1200ms: chon 33, dung 20   -> 13 luot chon SAI

Chon SAI tinh huong nghe nhu AI hieu nham - te hon la khong chon (ro chung van
trung tinh). Nen cau hoi dung la: siet nguong co doi duoc "chon sai" thanh
"khong chon" ma van giu phan "chon dung" khong?

Nhan = tinh huong cua CAU TRON (da qua luoi loc, duong that dung ban nay).

Chay:  .venv\\python.exe scripts\\do_nguong_tinh_huong.py
"""
import asyncio
import json
import sys
import wave
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.filler_situation import chon_tinh_huong, chuan_hoa  # noqa: E402
from backend.services.rag_service import RAGService  # noqa: E402
from backend.services.stt_service import STTService  # noqa: E402

VAO = DU_AN / "data" / "tieng_khach_that"
MOC_MS = [1000, 1200]
NGUONG = [0.75, 0.80, 0.85, 0.90]
SR = 16000


def doc_pcm(f: Path) -> bytes:
    with wave.open(str(f)) as w:
        return w.readframes(w.getnframes())


async def main():
    seed = json.loads((DU_AN / "data" / "tinh_huong_seed.json").read_text("utf-8"))
    ds = seed["tinh_huong"] if isinstance(seed, dict) else seed
    rag = RAGService(); rag.load()
    kho = {t["id"]: chuan_hoa(rag.embed(t["vi_du"])) for t in ds if t.get("vi_du")}
    stt = STTService()
    files = sorted(VAO.glob("*.wav"))

    # nhan tu cau TRON, dung nguong mac dinh
    nhan, chu_cut = {}, {}
    for f in files:
        chu = (await stt.transcribe(doc_pcm(f), sample_rate=SR)).strip()
        nhan[f.name] = (chon_tinh_huong(chuan_hoa(rag.embed([chu]))[0], kho)[0]
                        if len(chu) >= 4 else None)
    print(f"{len(files)} luot | {sum(1 for v in nhan.values() if v)} luot co nhan\n")

    # phien am san cac moc de khoi goi lai khi quet nguong
    for ms in MOC_MS:
        nb = int(SR * ms / 1000) * 2
        for f in files:
            pcm = doc_pcm(f)[:nb]
            chu_cut[(f.name, ms)] = ((await stt.transcribe(pcm, sample_rate=SR)).strip()
                                     if len(pcm) >= 640 else "")
    await stt.close()

    print(f"{'moc':>7} {'nguong':>7} | {'chon':>5} {'dung':>5} {'SAI':>5} | ty le dung")
    print("-" * 58)
    for ms in MOC_MS:
        for ng in NGUONG:
            chon = dung = sai = 0
            for f in files:
                chu = chu_cut[(f.name, ms)]
                if len(chu) < 4:
                    continue
                id_th, _ = chon_tinh_huong(chuan_hoa(rag.embed([chu]))[0], kho, nguong=ng)
                if id_th:
                    chon += 1
                    if id_th == nhan[f.name]:
                        dung += 1
                    else:
                        sai += 1
            ty = f"{dung/chon*100:.0f}%" if chon else "-"
            print(f"{ms:>5}ms {ng:>7.2f} | {chon:>5} {dung:>5} {sai:>5} | {ty}")

asyncio.run(main())
