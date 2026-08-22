"""F5 co that su NGHI o dau phay khong?

Doi chung: cung mot cau, chi khac CO hay KHONG co dau phay. Do cac quang lang
BEN TRONG manh (bo 2 dau). Neu ban co phay co quang lang o dung cho do con ban
khong co phay thi khong -> F5 ton trong phay. Neu ca hai deu khong -> F5 LO phay,
va vi phay KHONG phai cho cat manh nen khong co code nao chen nhip nghi ca.

Nguong theo RMS cua CHINH manh, khong theo bien do tuyet doi - tieng F5 co nhieu
nen, nguong tuyet doi luon sai.

Chay TREN MAY WIN:
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\do_nghi_o_phay.py [N]
"""
import base64
import io
import json
import sys
import urllib.parse
import urllib.request
import wave

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

TTS = "http://127.0.0.1:8100/api/voices/test-tts"
GIONG = "giong_heu"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
KHUNG = 0.01
TOI_THIEU_MS = 60          # quang ngan hon coi nhu khong phai cho nghi

CAP = [
    ("CO phay ", "Em là Dương, chuyên viên tư vấn tín dụng tại ngân hàng."),
    ("KHONG phay", "Em là Dương chuyên viên tư vấn tín dụng tại ngân hàng."),
    ("CO phay ", "Anh chị cứ yên tâm, hồ sơ duyệt trong hai tư giờ."),
    ("KHONG phay", "Anh chị cứ yên tâm hồ sơ duyệt trong hai tư giờ."),
]


def sinh(text):
    d = urllib.parse.urlencode({"text": text, "voice_name": GIONG}).encode()
    with urllib.request.urlopen(urllib.request.Request(TTS, data=d), timeout=300) as r:
        return json.load(r)


def quang_lang(b64):
    with wave.open(io.BytesIO(base64.b64decode(b64))) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    n = max(1, int(sr * KHUNG)); k = len(x) // n
    rms = np.sqrt((x[:k * n].reshape(k, n) ** 2).mean(axis=1))
    im = rms < rms.max() * 0.08
    # bo im lang o hai DAU - do la rim, khong phai cho nghi trong cau
    i = 0
    while i < len(im) and im[i]: i += 1
    j = len(im) - 1
    while j >= 0 and im[j]: j -= 1
    ra, dem, batdau = [], 0, 0
    for t in range(i, j + 1):
        if im[t]:
            if dem == 0: batdau = t
            dem += 1
        else:
            if dem * KHUNG * 1000 >= TOI_THIEU_MS:
                ra.append((batdau * KHUNG, dem * KHUNG * 1000))
            dem = 0
    if dem * KHUNG * 1000 >= TOI_THIEU_MS:
        ra.append((batdau * KHUNG, dem * KHUNG * 1000))
    return ra, len(x) / sr


def main():
    print(f"Giong {GIONG}, {N} lan moi cau, quang lang >= {TOI_THIEU_MS}ms\n")
    for nhan, cau in CAP:
        print(f"--- {nhan}: {cau}")
        for i in range(N):
            r = sinh(cau)
            if r.get("error"):
                print(f"    lan {i+1}: LOI {r['error']}"); continue
            q, dai = quang_lang(r["audio"])
            if q:
                mo_ta = ", ".join(f"{t:.2f}s:{ms:.0f}ms" for t, ms in q)
            else:
                mo_ta = "KHONG CO quang nghi nao"
            print(f"    lan {i+1}: dai {dai:5.2f}s | {len(q)} quang | {mo_ta}")
        print()


if __name__ == "__main__":
    main()
