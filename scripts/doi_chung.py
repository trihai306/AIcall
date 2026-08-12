"""Moc so sanh: cung checkpoint, cung 3 cau, doi giong mau sang 'giong_heu' (cu).

Muc dich: tach hai nguon loi. Neu giong cu cung sai o dung nhung tu do thi loi
la cua may nhan dang, khong phai cua giong moi.
"""
import base64
import difflib
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TTS = "http://127.0.0.1:8100/api/voices/test-tts"
WHISPER = "http://127.0.0.1:8178/inference"
RA = Path(r"C:\duan\chat-ai\logs\thu_giong")

CAU = {
    "01_da":  "Dạ em chào anh, em gọi từ ngân hàng ạ.",
    "02_so":  "Dạ lãi suất hiện tại là sáu phẩy năm phần trăm một năm, vay tối đa năm trăm triệu ạ.",
    "03_dai": ("Dạ bên em đang có gói vay tín chấp dành cho khách hàng có thu nhập ổn định, "
               "thủ tục đơn giản, giải ngân trong vòng hai mươi bốn giờ ạ."),
}


def chuan(s):
    return re.sub(r"[^\w\sÀ-ỹ]", "", unicodedata.normalize("NFC", s.lower())).strip()


for giong in ("giong_nam", "giong_heu"):
    tong_dung = tong_tu = 0
    print(f"--- giong mau: {giong} ---")
    for ten, goc in CAU.items():
        d = urllib.parse.urlencode({"text": goc, "voice_name": giong, "fast": "false"}).encode()
        with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=120) as r:
            kq = json.loads(r.read())
        if "error" in kq:
            print(f"  [{ten}] LOI: {kq['error']}")
            continue

        f = RA / f"{giong}_{ten}.wav"
        f.write_bytes(base64.b64decode(kq["audio"]))

        with f.open("rb") as fh:
            rr = requests.post(WHISPER, files={"file": (f.name, fh, "audio/wav")},
                               data={"language": "vi", "response_format": "verbose_json",
                                     "temperature": "0"}, timeout=120)
        nghe = (rr.json().get("text") or "").strip()

        a, b = chuan(goc).split(), chuan(nghe).split()
        khop = sum(k.size for k in difflib.SequenceMatcher(None, a, b).get_matching_blocks())
        tong_dung += khop
        tong_tu += len(a)
        thieu = [w for w in a if w not in b]
        print(f"  [{ten}] {khop}/{len(a)} ({khop/len(a)*100:.0f}%)"
              + (f"  lech: {' '.join(thieu[:6])}" if thieu else ""))
    print(f"  TONG {giong}: {tong_dung}/{tong_tu} = {tong_dung/tong_tu*100:.1f}%\n")
