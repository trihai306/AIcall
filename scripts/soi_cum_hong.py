"""Tim cum HONG LAP LAI trong 2566 luot phien am that -> ung vien luat sua chu.

Vi sao khong can nghe: mot cum vo nghia xuat hien NHIEU LAN qua nhieu phien thi
gan nhu chac chan la loi STT he thong chu khong phai khach noi vay. Day dung la
cach commit 5cc5919 tim ra "lon son" -> "han muc".

LOC LUOT DO STT SINH: `content[0].islower()`. Khong loc thi phan lon la chu toi
tu go luc test, va bang tan suat se phan anh tay toi chu khong phan anh may.
Xem memory `chat-ai-mat-dau-cau-khach`.

Cach cham diem ung vien: cum 2 tu xuat hien >= 2 lan, roi do khoang cach ky tu
toi cac TU KHOA NGHIEP VU. Gan ma khong trung = nhieu kha nang la bien the nghe
nham cua tu khoa do.

Chay:  .venv\\python.exe scripts\\soi_cum_hong.py
"""
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

DU_AN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DU_AN))
sys.stdout.reconfigure(encoding="utf-8")

DB = DU_AN / "data" / "app.db"
RA = DU_AN / "data" / "ket_cum_hong.txt"

# Tu khoa nghiep vu - thu ma khach THUC SU hay hoi
KHOA = ["lãi suất", "hạn mức", "tín chấp", "vay tín chấp", "thủ tục",
        "điều kiện", "hồ sơ", "trả góp", "giải ngân", "thu nhập",
        "sao kê", "căn cước", "chứng minh", "thế chấp", "ngân hàng"]


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")


def main():
    if not DB.exists():
        print("khong thay app.db"); return
    cn = sqlite3.connect(str(DB))
    luot = [r[0] for r in cn.execute(
        "SELECT content FROM conversation_turns WHERE role='user'")]
    cn.close()
    # chi giu luot do STT sinh (chu thuong dau cau), bo luot go tay khi test
    stt = [t for t in luot if t and t[0].islower()]
    print(f"{len(luot)} luot tong -> {len(stt)} luot do STT sinh")

    cum, tu_le = Counter(), Counter()
    for t in stt:
        tu = re.findall(r"[a-zA-ZÀ-ỹ]+", t.lower())
        tu_le.update(tu)
        for i in range(len(tu) - 1):
            cum[f"{tu[i]} {tu[i+1]}"] += 1

    # Cum ma MOI TU deu pho bien thi gan nhu chac la tieng Viet that ("anh muon",
    # "nhu nao") - loai di, khong thi bang toan duong tinh gia. Loi STT hay de ra
    # tu HIEM ("lon son", "tinh chop"), do la dau hieu dang tin hon do giong.
    POHBIEN = 25

    khoa_bd = {k: bo_dau(k) for k in KHOA}
    ung_vien = []
    for c, n in cum.items():
        if n < 2 or c in khoa_bd:
            continue
        cbd = bo_dau(c)
        for k, kbd in khoa_bd.items():
            if cbd == kbd:
                break
            r = SequenceMatcher(None, cbd, kbd).ratio()
            # gan ma khong trung -> nhieu kha nang la bien the nghe nham
            if 0.75 <= r < 1.0 and min(tu_le[w] for w in c.split()) < POHBIEN:
                ung_vien.append((n, round(r, 2), c, k, min(tu_le[w] for w in c.split())))
                break

    ung_vien.sort(key=lambda x: (-x[0], -x[1]))
    dong = [f"{len(stt)} luot STT | {len(cum)} cum 2 tu | "
            f"{len(ung_vien)} ung vien nghe nham", "",
            f"{'lan':>4} {'giong':>6}  {'cum nghe duoc':<28} {'co the la':<16}",
            "-" * 70]
    for n, r, c, k, hiem in ung_vien[:40]:
        dong.append(f"{n:>4} {r:>6}  {c:<28} {k:<16} (tu hiem nhat: {hiem} lan)")
    RA.write_text("\n".join(dong), encoding="utf-8")
    print("\n".join(dong[:50]))
    print(f"\n-> {RA}")

main()
