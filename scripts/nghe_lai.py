"""Cho PhoWhisper nghe lai chinh file TTS vua sinh, so voi chu goc.

VI SAO PHEP DO NAY DANG TIN: no khong hoi y kien ai ca. Neu may nhan dang
chep lai dung tung chu thi giong ro rang; sai chu nao thi chinh chu do nguoi
that cung se nghe khong ro. Rat hop de bat loi "Da" bi doc thanh "gia".
"""
import difflib
import re
import sys
import unicodedata
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WHISPER = "http://127.0.0.1:8178/inference"
THU_MUC = Path(r"C:\duan\chat-ai\logs\thu_giong")

GOC = {
    "01_da":  "Dạ em chào anh, em gọi từ ngân hàng ạ.",
    "02_so":  "Dạ lãi suất hiện tại là sáu phẩy năm phần trăm một năm, vay tối đa năm trăm triệu ạ.",
    "03_dai": ("Dạ bên em đang có gói vay tín chấp dành cho khách hàng có thu nhập ổn định, "
               "thủ tục đơn giản, giải ngân trong vòng hai mươi bốn giờ ạ."),
}


def chuan(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    return re.sub(r"[^\w\sÀ-ỹ]", "", s).strip()


tong_dung = tong_tu = 0
for ten, goc in GOC.items():
    f = THU_MUC / f"{ten}.wav"
    if not f.exists():
        print(f"[{ten}] thieu file")
        continue

    with f.open("rb") as fh:
        r = requests.post(WHISPER,
                          files={"file": (f.name, fh, "audio/wav")},
                          data={"language": "vi", "response_format": "verbose_json",
                                "temperature": "0"},
                          timeout=120)
    nghe = (r.json().get("text") or "").strip()

    a, b = chuan(goc).split(), chuan(nghe).split()
    # Ty le tu khop, tinh theo difflib de khong phat oan khi lech mot tu o dau.
    khop = sum(k.size for k in difflib.SequenceMatcher(None, a, b).get_matching_blocks())
    tong_dung += khop
    tong_tu += len(a)

    print(f"[{ten}] khop {khop}/{len(a)} tu ({khop/len(a)*100:.0f}%)")
    print(f"   goc  : {goc}")
    print(f"   nghe : {nghe}")
    if khop < len(a):
        thieu = [w for w in a if w not in b]
        if thieu:
            print(f"   lech : {' '.join(thieu[:8])}")
    print()

print(f"TONG: {tong_dung}/{tong_tu} tu = {tong_dung/tong_tu*100:.1f}% khop")
