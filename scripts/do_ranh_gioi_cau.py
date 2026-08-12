"""Cho ngat CAU nam GIUA mot manh thi F5 co nghi khong?

Trieu chung: "doc cam giac de len nhau" - het cau nay dinh luon vao cau sau.

Duong di hien tai:
  - `bo_dau_cau_cho_f5` BO dau cham truoc khi dua vao F5  -> F5 khong biet het cau
  - `nhip_nghi_sau` tra 0.0 khi CAT_DON_GIAN               -> code cung khong chen
Nen o moi ranh gioi cau, ca hai duong deu khong tao ra khoang nghi nao.

Do: sinh DUNG mot manh chua dung mot ranh gioi cau, do khoang lang tai dung cho
do, o hai che do bo dau / giu dau. Lap nhieu lan vi F5 lay mau ngau nhien.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\do_ranh_gioi_cau.py --lan 4
"""
import argparse
import asyncio
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

import backend.services.tts_service as mod                       # noqa: E402
from backend.pipeline.text_normalizer import normalize_for_tts   # noqa: E402
from backend.services.tts_service import F5TTSService            # noqa: E402

STT = "http://127.0.0.1:8178/inference"
KHUNG_MS = 20.0

# Mot manh 20 tu, ranh gioi cau nam DUNG GIUA (sau "the chap gi het.").
MANH = ("bên em đang có chương trình vay tín chấp anh không cần thế chấp gì hết. "
        "Lãi suất hiện tại từ bảy phẩy chín phần trăm")
# Tu ngay TRUOC ranh gioi, de dinh vi bang STT khong duoc thi dinh vi bang ty le.
TI_LE_RANH = 11 / 20.0          # ranh gioi nam sau tu thu 11 / 20 tu


def nghe_lai(x, sr) -> str:
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--" + bd + b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            + b.getvalue() + b"\r\n--" + bd + b"--\r\n")
    r = urllib.request.Request(
        STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r, timeout=180).read()).get("text", "").strip()


def cac_quang_lang(x, sr):
    """[(bat_dau_giay, dai_ms)] moi quang lang nam GIUA manh."""
    n = max(1, int(sr * KHUNG_MS / 1000))
    k = len(x) // n
    if k < 3:
        return []
    kh = x[: k * n].reshape(k, n).astype(np.float64)
    rms = np.sqrt((kh * kh).mean(axis=1))
    dinh = float(rms.max())
    im = rms < dinh * 0.20
    day = dinh * 0.07
    ra, i = [], 0
    while i < k:
        j = i
        while j < k and im[j] == im[i]:
            j += 1
        dai = (j - i) * KHUNG_MS
        if im[i] and i > 0 and j < k and dai > 80 and float(rms[i:j].min()) < day:
            ra.append((i * KHUNG_MS / 1000, dai))
        i = j
    return ra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", type=int, default=4)
    ap.add_argument("--he-so", type=float, default=None)
    a = ap.parse_args()
    if a.he_so:
        mod.HE_SO_BU_LANG = a.he_so

    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    goc = mod.bo_dau_cau_cho_f5

    print(f"\n  giọng {ten}   hệ số cấp {mod.HE_SO_BU_LANG}")
    print(f"  mảnh: \"{MANH}\"")
    print(f"  ranh giới câu nằm sau từ thứ 11/20 (~{TI_LE_RANH:.0%} chiều dài)\n")
    print(f"  {'chế độ':>12} {'lần':>4} {'nghỉ ở ranh giới':>18} {'quãng lặng khác':>17}")
    print("  " + "-" * 58)

    for nhan, ham in (("BỎ dấu (nay)", lambda t: goc(t)), ("GIỮ dấu", lambda t: t)):
        mod.bo_dau_cau_cho_f5 = ham
        tai_ranh, khac = [], []
        for r in range(a.lan):
            y, sr = svc._synthesize_sync(MANH, ten)
            y = mod.trim_silence(y, sr)
            dai = len(y) / sr
            qs = cac_quang_lang(y, sr)
            # Quang nao nam gan vi tri ranh gioi (+-12% chieu dai) thi tinh la
            # "nghi o ranh gioi"; con lai la quang bia o cho khac.
            gan = [d for (t, d) in qs if abs(t / dai - TI_LE_RANH) < 0.12]
            xa = [d for (t, d) in qs if abs(t / dai - TI_LE_RANH) >= 0.12]
            tai_ranh.append(max(gan) if gan else 0.0)
            khac.append(len(xa))
            print(f"  {nhan:>12} {r + 1:>4} {(max(gan) if gan else 0):>15.0f}ms"
                  f" {len(xa):>13} quãng")
        print(f"  {'':>12} {'TB':>4} {np.mean(tai_ranh):>15.0f}ms"
              f" {np.mean(khac):>13.1f} quãng")
        print("  " + "-" * 58)

    mod.bo_dau_cau_cho_f5 = goc
    print("\n  'nghỉ ở ranh giới' = 0ms nghĩa là hai câu dính liền nhau -")
    print("  đúng thứ người dùng nghe thành 'đọc đè lên nhau'.")
    print("  Nghỉ thật của người ở dấu chấm: khoảng 300-450ms.\n")


if __name__ == "__main__":
    main()
