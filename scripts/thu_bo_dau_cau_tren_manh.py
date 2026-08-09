"""Bo DAU CHAM/PHAY khoi chu gui cho F5, tren MANH 5 TU - duoc gi mat gi.

Lan truoc do tren CA CAU nen khong thay gi (7% -> 8%). Cho co van de la manh
5 tu: lech nhip 31%. Phai do dung o do.

Y: manh 5 tu bi cat giua chung nen dau cau roi vao cho tuy tien - manh nay ket
thuc bang dau phay, manh kia khong. F5 nghi o dau cau, nen manh co dau va manh
khong dau ra hai nhip khac nhau. Bo het dau di thi moi manh giong nhau.

Diem quan trong: van GIU dau de tinh nhip nghi (`nhip_nghi_sau`), chi bo khoi
chu DUA VAO F5. Nhu the cho ngat cau khong mat, ma F5 khong con co dau de nghi
tuy tien.

Do ba thu:
    - lech nhip giua cac manh
    - quang lang > 300ms ben trong manh (F5 nghi o dau cau)
    - chu con doc dung bao nhieu

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\thu_bo_dau_cau_tren_manh.py
"""
import asyncio
import difflib
import io
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np              # noqa: E402
import soundfile as sf          # noqa: E402

from backend.services.tts_service import F5TTSService  # noqa: E402

STT = "http://127.0.0.1:8178/inference"
RA = Path("C:/tmp/bodaucaumanh")
NGUONG_IM, KHUNG = 0.015, 0.02

VAN = ("Dạ vâng ạ, với tình hình thu nhập của anh chị thì em có thể tư vấn hạn mức "
       "lên đến năm trăm triệu đồng, thời hạn vay linh hoạt từ mười hai đến sáu mươi "
       "tháng, và lãi suất áp dụng từ bảy phẩy chín phần trăm một năm ạ. Anh chị chuẩn "
       "bị giúp em chứng minh nhân dân, sổ hộ khẩu và sao kê lương ba tháng gần nhất, "
       "thì bên em xử lý rất nhanh ạ.")


def bo_dau_cau(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[,.;:!?…]", " ", s)).strip()


def chuan(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


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


def am_tiet(s):
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def _khung(x, sr):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    if k == 0:
        return np.array([], dtype=bool), 0
    return np.abs(x[: k * n].reshape(k, n)).max(axis=1) < NGUONG_IM, k


def giay_co_tieng(x, sr):
    im, k = _khung(x, sr)
    return float((~im).sum() * KHUNG) if k else len(x) / sr


def lang_giua(x, sr, tt=300):
    im, k = _khung(x, sr)
    ra, i = [], 0
    while i < k:
        if im[i]:
            j = i
            while j < k and im[j]:
                j += 1
            if i > 0 and j < k and (j - i) * 20 >= tt:
                ra.append((j - i) * 20)
            i = j
        else:
            i += 1
    return ra


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    RA.mkdir(parents=True, exist_ok=True)

    tu = VAN.split()
    manh_goc = [" ".join(tu[i:i+5]) for i in range(0, len(tu), 5)]

    print(f"\n  giọng {ten}   speed {svc.toc_do_cua(ten):.2f}   {len(manh_goc)} mảnh 5 từ\n")
    print(f"  {'bản':<22} {'nhịp trung vị':>14} {'lệch':>7} {'lặng giữa':>11} {'chữ đúng':>10}")
    print("  " + "-" * 68)

    for nhan, bien_doi in (("giữ nguyên dấu", lambda s: s),
                           ("BỎ dấu chấm/phẩy", bo_dau_cau)):
        nhips, lang, manh_wav = [], 0, []
        for c in manh_goc:
            gui = bien_doi(c)
            if not gui.strip():
                continue
            b = asyncio.run(svc.synthesize(gui, voice=ten))
            x, sr = sf.read(io.BytesIO(b), dtype="float32")
            if x.ndim > 1:
                x = x.mean(axis=1)
            t = nghe_lai(x, sr)
            g = giay_co_tieng(x, sr)
            n = am_tiet(t)
            if n >= 2 and g > 0.2:
                nhips.append(n / g * 60)
            lang += len(lang_giua(x, sr))
            manh_wav.append(x / max(1.0, float(np.abs(x).max())))
        y = np.concatenate(manh_wav)
        sf.write(RA / f"{chuan(nhan).replace(' ', '_')}.wav", y, sr)
        # Chu dung: nghe lai CA BAN ghep roi so voi van goc
        dung = difflib.SequenceMatcher(
            None, chuan(VAN).split(), chuan(nghe_lai(y, sr)).split()).ratio() * 100
        tv = float(np.median(nhips)) if nhips else 0
        lech = (max(nhips) - min(nhips)) / tv * 100 if nhips else 0
        print(f"  {nhan:<22} {tv:>13.0f} {lech:>6.0f}% {lang:>10} {dung:>9.0f}%")

    print("  " + "-" * 68)
    print(f"\n  'lặng giữa' = số quãng > 300ms nằm trong lòng mảnh, gộp cả {len(manh_goc)} mảnh.")
    print(f"\n  wav ở {RA}")


if __name__ == "__main__":
    main()
