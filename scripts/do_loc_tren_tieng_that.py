"""Luoi loc phien am dang lam gi tren 102 luot TIENG KHACH THAT?

Phep A/B cau moi truoc do goi THANG `/inference` nen BO QUA tang loc cua backend
(`STTService._dang_ngo`) - do mot duong khong ton tai trong san xuat. Day la
phep do tren DUNG duong that.

Cau hoi:
  1. Bao nhieu luot bi loc, ly do gi?
  2. Cau bia dai ("co them mot doan truyen ngan cho cac thi sinh...") co bi bat?
  3. Loc co vut nham luot that khong?

Chay:  .venv\\python.exe scripts\\do_loc_tren_tieng_that.py
"""
import asyncio
import io
import sys
import wave
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.services.stt_service import STTService   # noqa: E402

VAO = DU_AN / "data" / "tieng_khach_that"
RA = DU_AN / "data" / "ket_loc_tieng_that.txt"


def pcm_cua(f: Path) -> tuple[bytes, float]:
    with wave.open(str(f)) as w:
        n, sr = w.getnframes(), w.getframerate()
        return w.readframes(n), n / sr


async def main():
    stt = STTService()
    files = sorted(VAO.glob("*.wav"))
    print(f"{len(files)} luot | health={await stt.health_check()}")

    giu, bo = [], []
    for i, f in enumerate(files):
        pcm, giay = pcm_cua(f)
        # duong THAT: transcribe() da goi _dang_ngo ben trong
        chu = (await stt.transcribe(pcm, sample_rate=16000)).strip()
        if chu:
            giu.append((f.name, giay, chu))
        else:
            bo.append((f.name, giay))
        if (i + 1) % 25 == 0:
            print(f"  ...{i+1}/{len(files)}", flush=True)
    await stt.close()

    dong = [f"TONG {len(files)} luot: GIU {len(giu)} | BO {len(bo)}", ""]
    dong.append("=== GIU LAI (loc cho qua) ===")
    for ten, giay, chu in giu:
        # chu/giay cao bat thuong = dau hieu bia
        n = len(chu.split())
        dong.append(f"  {giay:4.1f}s {n:>2}tu {n/max(giay,0.1):4.1f}tu/s  {chu[:66]!r}")
    dong.append("")
    dong.append("=== BI BO ===")
    for ten, giay in bo:
        dong.append(f"  {giay:4.1f}s  {ten}")
    RA.write_text("\n".join(dong), encoding="utf-8")
    print(f"\nGIU {len(giu)} | BO {len(bo)}  -> {RA}")

asyncio.run(main())
