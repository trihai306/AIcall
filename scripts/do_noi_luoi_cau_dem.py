"""Noi luoi loc CHO RIENG duong cau dem thi co giup khong?

Van de: `speculate()` goi `STTService.transcribe`, ham nay tra CHUOI RONG khi
ban phien am dang ngo (`_dang_ngo`). Tren luot khach ngan (0,9-1,3s - phan lon
luot that) ban tam bi vut, nen `spec_stt` rong va cau dem khong phan loai duoc
tinh huong. Do duoc: chi 2/80 luot cuoc goi that co tinh huong.

Y tuong sua: cho rieng duong CHON CAU DEM dung ban THO (chua qua luoi loc).
Chon sai cau dem hai NHE, con nhan sai loi khach hai NANG - hai duong nay khong
can chung mot nguong tin cay.

NHUNG phai do truoc khi sua: co chu chua chac du de phan loai DUNG. Neu ban tho
chi doi "khong chon duoc" thanh "chon SAI" thi te hon, vi khach nghe nhu AI hieu
nham.

Script do tren 7 luot tieng that, cat theo cac moc thoi gian mo phong ban tam:
  - ban LOC : `transcribe()` (duong hien tai)
  - ban THO : `_goi_whisper()` (bo qua `_dang_ngo`)
va cham ca hai theo nhan = tinh huong cua CAU TRON.

Chay:  .venv\\python.exe scripts\\do_noi_luoi_cau_dem.py
"""
import asyncio
import io
import json
import sys
import wave
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings  # noqa: E402
from backend.services.filler_situation import (NGUONG_DIEM, chon_tinh_huong,  # noqa: E402
                                               chuan_hoa)
from backend.services.rag_service import RAGService  # noqa: E402
from backend.services.stt_service import STTService, moi_tu_vung  # noqa: E402

VAO = DU_AN / "data" / "tieng_khach_that"   # 102 luot trich tu 47 ban ghi
MOC_MS = [600, 800, 1000, 1200]
SR = 16000


def wav_cua(pcm: bytes) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
    return b.getvalue()


async def main():
    seed = json.loads((DU_AN / "data" / "tinh_huong_seed.json").read_text("utf-8"))
    ds = seed["tinh_huong"] if isinstance(seed, dict) else seed
    rag = RAGService(); rag.load()
    kho = {t["id"]: chuan_hoa(rag.embed(t["vi_du"])) for t in ds if t.get("vi_du")}
    stt = STTService()
    moi = moi_tu_vung(settings.stt_vung_mien)

    def phan_loai(chu: str):
        if not chu or len(chu) < 4:
            return None
        return chon_tinh_huong(chuan_hoa(rag.embed([chu]))[0], kho)[0]

    def doc_pcm(f: Path) -> bytes:
        with wave.open(str(f)) as w:
            return w.readframes(w.getnframes())

    files = sorted(VAO.glob("*.wav"))
    nhan = {}
    for f in files:
        chu = (await stt.transcribe(doc_pcm(f), sample_rate=SR)).strip()
        nhan[f.name] = phan_loai(chu)
    co_nhan = [f for f in files if nhan[f.name]]
    print(f"{len(files)} luot | {len(co_nhan)} luot co nhan (cau tron phan loai duoc)")
    print(f"NGUONG_DIEM = {NGUONG_DIEM}\n")

    print(f"{'moc':>7} | {'LOC: chon/dung':>16} | {'THO: chon/dung':>16} | THO chon SAI")
    print("-" * 70)
    for ms in MOC_MS:
        n_byte = int(SR * ms / 1000) * 2
        l_chon = l_dung = t_chon = t_dung = t_sai = 0
        for f in files:
            pcm = doc_pcm(f)[:n_byte]
            if len(pcm) < 640:
                continue
            loc = (await stt.transcribe(pcm, sample_rate=SR)).strip()
            kq = await stt._goi_whisper(wav_cua(pcm), moi)
            tho = (kq[0] if kq else "").strip()
            for chu, (c, d, s) in ((loc, ("l", 0, 0)), (tho, ("t", 0, 0))):
                pass
            id_l, id_t = phan_loai(loc), phan_loai(tho)
            if id_l:
                l_chon += 1
                if id_l == nhan[f.name]:
                    l_dung += 1
            if id_t:
                t_chon += 1
                if id_t == nhan[f.name]:
                    t_dung += 1
                else:
                    t_sai += 1
        print(f"{ms:>5}ms | {l_chon:>7}/{l_dung:<8} | {t_chon:>7}/{t_dung:<8} | {t_sai}")
    await stt.close()
    print("\n'chon' = phan loai ra mot tinh huong | 'dung' = trung tinh huong cua cau tron")
    print("THO chon SAI = so luot ban tho chon mot tinh huong KHAC cau tron -> hai")

asyncio.run(main())
