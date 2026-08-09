"""Bo DAU THANH hoac DAU CAU truoc khi dua vao TTS thi duoc gi, mat gi.

Vi sao thu: da do duoc F5 cap thoi luong theo so BYTE, ma chu tieng Viet co dau
ton 3 byte con chu khong dau ton 1. Tuong quan byte/am tiet voi nhip doc ra la
-0.74. Bo het dau thi moi chu ve cung mat do byte -> nhip le ra phai deu.

Nhung phai kiem CHU CO CON DOC DUNG KHONG. Tieng Viet bo dau la mat thanh dieu:
"lãi" thanh "lai", "một" thanh "mot". Nhip deu ma khach nghe sai chu thi vo
nghia. Nen script do hai thu cung luc:
    - nhip doc ra va do lech giua cac cau
    - CHU con dung bao nhieu: cho STT nghe lai roi so voi cau goc

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\thu_bo_dau.py
"""
import asyncio
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
RA = Path("C:/tmp/bodau")
NGUONG_IM, KHUNG = 0.015, 0.02

CAU = [
    "Dạ vâng ạ, để em kiểm tra lại giúp anh chị nhé",
    "Lãi suất bên em là bảy phẩy chín phần trăm một năm",
    "Hạn mức tối đa năm trăm triệu, thời hạn sáu mươi tháng",
    "Anh chị chuẩn bị chứng minh nhân dân và sổ hộ khẩu",
    "Sau khi phê duyệt thì bên em giải ngân trong hai mươi bốn giờ",
    "Anh chị cho em xin ít phút để em tư vấn kỹ hơn ạ",
]


def bo_dau_thanh(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", s).replace("đ", "d").replace("Đ", "D")


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


def giong_bao_nhieu(goc: str, nghe: str) -> float:
    """Bao nhieu % chu cua cau goc con nghe ra dung, theo dung THU TU."""
    a, b = chuan(goc).split(), chuan(nghe).split()
    if not a:
        return 0.0
    import difflib
    kh = difflib.SequenceMatcher(None, a, b)
    return kh.ratio() * 100


def giay_co_tieng(x, sr):
    n = max(1, int(sr * KHUNG))
    k = len(x) // n
    if k == 0:
        return len(x) / sr
    to = np.abs(x[: k * n].reshape(k, n)).max(axis=1)
    return float((to >= NGUONG_IM).sum() * KHUNG)


def am_tiet(s):
    return len([t for t in re.split(r"\s+", s.strip()) if re.search(r"\w", t)])


def main():
    svc = F5TTSService()
    svc.load()
    ten = svc.default_voice_name()
    asyncio.run(svc.ensure_voice(ten))
    RA.mkdir(parents=True, exist_ok=True)

    BAN = [
        ("giữ nguyên", lambda s: s),
        ("bỏ DẤU THANH", bo_dau_thanh),
        ("bỏ DẤU CÂU", bo_dau_cau),
    ]

    print(f"\n  giọng {ten}   speed {svc.toc_do_cua(ten):.2f}\n")
    ket = {}
    for nhan, f in BAN:
        nhips, giong = [], []
        manh = []
        for c in CAU:
            gui = f(c)
            b = asyncio.run(svc.synthesize(gui, voice=ten))
            x, sr = sf.read(io.BytesIO(b), dtype="float32")
            if x.ndim > 1:
                x = x.mean(axis=1)
            t = nghe_lai(x, sr)
            g = giay_co_tieng(x, sr)
            n = am_tiet(t)
            if n >= 2 and g > 0.2:
                nhips.append(n / g * 60)
            # So voi cau GOC co dau, khong so voi cau da bo dau: dich la khach
            # phai nghe ra dung chu goc.
            giong.append(giong_bao_nhieu(c, t))
            manh.append(x / max(1.0, float(np.abs(x).max())))
            manh.append(np.zeros(int(sr * 0.35), dtype=np.float32))
        sf.write(RA / f"{chuan(nhan).replace(' ', '_')}.wav", np.concatenate(manh), sr)
        ket[nhan] = (nhips, giong)

    print(f"  {'bản':<16} {'nhịp trung vị':>14} {'lệch nhịp':>11} {'chữ đúng':>10}")
    print("  " + "-" * 56)
    for nhan, (nhips, giong) in ket.items():
        if not nhips:
            print(f"  {nhan:<16} STT không đọc được")
            continue
        tv = float(np.median(nhips))
        lech = (max(nhips) - min(nhips)) / tv * 100
        print(f"  {nhan:<16} {tv:>13.0f} {lech:>10.0f}% {np.mean(giong):>9.0f}%")
    print("  " + "-" * 56)
    print("\n  'chữ đúng' = STT nghe lại rồi so với câu GỐC CÓ DẤU. Dưới ~90% là")
    print("  khách nghe ra chữ khác - nhịp đều đến mấy cũng không dùng được.")
    print(f"\n  wav ở {RA}")


if __name__ == "__main__":
    main()
