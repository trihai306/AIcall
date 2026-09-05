"""A/B cau moi tu vung tren TIENG KHACH THAT, qua dung `/inference`.

Memory `chat-ai-phowhisper-large` do 05-09-2026: moi lam ROI TU DAU CAU
(medium +moi 2/18, -moi 0/18) va CER kenh 8k te hon (0,0148 vs 0,0094). Nhung
do do nap thang WhisperModel tren tieng F5, nen CHUA doi cau hinh san xuat.
Memory dan ro dieu kien de chot: A/B qua dung `/inference`, tren TIENG THU THAT.

Day la phep do do. 102 luot khach trich tu 12 ban ghi cuoc goi that
(`scripts/trich_tieng_khach.py`) - tieng nay da qua GSM/AMR that.

KHONG CO NHAN DUNG, nen do hai thu do duoc khach quan:

  1. HAU TO: ban +moi la hau to cua ban -moi (vd "cho anh hoi..." -> "anh hoi...")
     -> bang chung truc tiep cua "nuot tu dau cau", khong can biet loi that.
  2. So cau hai cau hinh BAT DONG -> loc ra cho tai nguoi phan.

Chay XEN KE hai chieu: luot chan goi +moi truoc, luot le goi -moi truoc. Khong
the thi khong biet minh dang do cau hinh hay do vi tri (bay ham may, xem
`chat-ai-tai-may-nghe-kem`).

Chay:  .venv\\python.exe scripts\\ab_moi_tren_tieng_that.py
"""
import json
import sys
import urllib.request
import uuid
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

from backend.config import settings          # noqa: E402
from backend.services.stt_service import moi_tu_vung   # noqa: E402

VAO = DU_AN / "data" / "tieng_khach_that"
RA = DU_AN / "data" / "ket_ab_moi.txt"
URL = settings.whisper_server_url


def goi(wav: bytes, moi: str | None) -> str:
    ranh = uuid.uuid4().hex
    than = b""
    than += (f'--{ranh}\r\nContent-Disposition: form-data; name="file"; '
             f'filename="a.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()
    than += wav + b"\r\n"
    if moi is not None:
        than += (f'--{ranh}\r\nContent-Disposition: form-data; name="prompt"'
                 f'\r\n\r\n{moi}\r\n').encode()
    than += f"--{ranh}--\r\n".encode()
    rq = urllib.request.Request(
        f"{URL}/inference", data=than,
        headers={"Content-Type": f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(rq, timeout=90) as r:
        return (json.loads(r.read().decode()).get("text") or "").strip()


def chuan(s: str) -> str:
    return " ".join(s.lower().replace(".", " ").replace(",", " ").split())


def main():
    files = sorted(VAO.glob("*.wav"))
    if not files:
        print("Chua co tieng - chay scripts/trich_tieng_khach.py truoc"); return
    moi = moi_tu_vung(settings.stt_vung_mien)
    print(f"{len(files)} luot | may chu: {URL}")
    print(f"moi: {moi[:70]!r}\n")

    giong = khac = hau_to_moi = hau_to_khong = 0
    dong = []
    for i, f in enumerate(files):
        wav = f.read_bytes()
        # xen ke thu tu de khong do nham vi tri thay vi cau hinh
        if i % 2 == 0:
            co, khong = goi(wav, moi), goi(wav, None)
        else:
            khong, co = goi(wav, None), goi(wav, moi)
        a, b = chuan(co), chuan(khong)
        if a == b:
            giong += 1
            continue
        khac += 1
        # ban nao NUOT TU DAU cua ban kia?
        nhan = ""
        if a and b.endswith(a) and len(b) > len(a):
            hau_to_moi += 1
            nhan = "  <<< CO MOI nuot dau cau"
        elif b and a.endswith(b) and len(a) > len(b):
            hau_to_khong += 1
            nhan = "  <<< KHONG MOI nuot dau cau"
        dong.append(f"{f.name}{nhan}\n   +moi : {co!r}\n   -moi : {khong!r}")
        if len(dong) % 10 == 0:
            print(f"  ...{i+1}/{len(files)}", flush=True)

    tom = [
        f"TONG: {len(files)} luot",
        f"  giong nhau            : {giong}",
        f"  khac nhau             : {khac}",
        f"  CO MOI nuot dau cau   : {hau_to_moi}",
        f"  KHONG MOI nuot dau cau: {hau_to_khong}",
        "", "=" * 70, "",
    ]
    RA.write_text("\n".join(tom + dong), encoding="utf-8")
    print("\n".join(tom[:5]))
    print(f"\n-> {RA}")

main()
