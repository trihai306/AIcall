"""Luat DO PHU co that su chan duoc phan loai SAI khong?

Chay:  .venv\\python.exe scripts\\do_do_phu_tinh_huong.py

Dung khi ai do dinh HA `NGUONG_CAU_DEM`: bo lui do phu roi thi chi con nguong
diem gac cua, ha no la phai chay lai bang nay truoc.

Doi chieu ban CAT (cham o NGUONG_CAU_DEM=0.90, dung do_phu = ti le BYTE AUDIO)
voi nhan cua cau TRON. Nhan lay o nguong 0.75 de CO nhan ma doi chieu - dung
0.90 thi 96/102 luot khong co nhan nao va phep so thanh vo nghia.

Ba o dem tach bach:
  DUNG  - ban cat va cau tron cho CUNG mot tinh huong
  SAI   - cho tinh huong KHAC nhau  (day moi la cai luat do phu sinh ra de chan)
  ?     - cau tron khong co nhan nao, khong phan xu duoc
"""
import json, sys, wave
from pathlib import Path
DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")
import asyncio  # noqa: E402
from backend.services.filler_situation import (NGUONG_CAU_DEM, NGUONG_DIEM,  # noqa: E402
                                               chon_tinh_huong, chuan_hoa)
from backend.services.rag_service import RAGService  # noqa: E402
from backend.services.stt_service import STTService  # noqa: E402

# Nguong cham ban CAT. Mac dinh la nguong duong that dang dung; truyen tham so
# de THU truoc khi doi, vi do chinh la luc phai chay lai bang nay.
#     .venv\\python.exe scripts\\do_do_phu_tinh_huong.py 0.75
NGUONG = float(sys.argv[1]) if len(sys.argv) > 1 else NGUONG_CAU_DEM

VAO = DU_AN / "data" / "tieng_khach_that"
SR = 16000
TY_LE = [0.15, 0.25, 0.35, 0.45, 0.55, 0.7, 0.85]


def pcm(f):
    with wave.open(str(f)) as w:
        return w.readframes(w.getnframes())


async def main():
    seed = json.loads((DU_AN / "data" / "tinh_huong_seed.json").read_text("utf-8"))
    ds = seed["tinh_huong"] if isinstance(seed, dict) else seed
    rag = RAGService(); rag.load()
    kho = {t["id"]: chuan_hoa(rag.embed(t["vi_du"])) for t in ds if t.get("vi_du")}
    stt = STTService()
    files = sorted(VAO.glob("*.wav"))

    def cham(chu, ng):
        if len(chu) < 4:
            return None
        return chon_tinh_huong(chuan_hoa(rag.embed([chu]))[0], kho, nguong=ng)[0]

    nhan = {}
    for f in files:
        nhan[f.name] = cham((await stt.transcribe(pcm(f), sample_rate=SR)).strip(),
                            NGUONG_DIEM)
    print(f"{len(files)} luot tieng khach that | cau TRON co nhan (0.75): "
          f"{sum(1 for v in nhan.values() if v)}")
    print(f"ban CAT cham o nguong {NGUONG}\n")
    print(f"{'do_phu':>7}{'qua nguong':>12}{'DUNG':>7}{'SAI':>6}{'?':>4}   luat hien nay")
    print("-" * 74)
    tong_vut_dung = tong_vut_sai = 0
    for ty in TY_LE:
        qua = dung = sai = kxd = 0
        for f in files:
            b = pcm(f)
            n = max(2, int(len(b) * ty)) // 2 * 2
            r = cham((await stt.transcribe(b[:n], sample_rate=SR)).strip(),
                     NGUONG)
            if not r:
                continue
            qua += 1
            if nhan[f.name] is None:
                kxd += 1
            elif r == nhan[f.name]:
                dung += 1
            else:
                sai += 1
        vut = ty < 0.5
        if vut:
            tong_vut_dung += dung; tong_vut_sai += sai
        print(f"{ty:>7.2f}{qua:>12}{dung:>7}{sai:>6}{kxd:>4}   "
              f"{'VUT DI' if vut else 'giu lai'}")
    print(f"\nPhan bi luat vut di (do_phu < 0.5): DUNG {tong_vut_dung}, SAI {tong_vut_sai}")

asyncio.run(main())
