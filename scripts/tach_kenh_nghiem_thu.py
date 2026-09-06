"""Tách hai kênh của bản ghi cuộc gọi rồi nghiệm thu RIÊNG giọng và nội dung.

VÌ SAO TÁCH. Bản ghi của hệ thống là STEREO: trái = khách, phải = AI (xem
`services/recorder.py`). Nghe lẫn cả hai thì không phán được gì - tiếng khách át
tiếng AI, và mọi số đo đều là số đo của hỗn hợp. Tách ra rồi mới nghiệm thu được
hai thứ vốn hỏng theo hai kiểu khác hẳn nhau:

    GIỌNG    - AI đọc có ra đúng chữ không, có âm rác không   -> kênh phải
    NỘI DUNG - AI trả lời có đúng không                        -> đối chiếu chữ

CẢNH BÁO ĐO, đã mắc thật 05-09-2026: kênh AI trong bản ghi ở khoảng -42 dBFS
(cố ý, vì đường tiêm của máy khuếch đại sẵn ~19 dB). Chuẩn đỉnh nó lên cho STT
nghe được thì khuếch đại luôn nhiễu nền, và PhoWhisper BỊA chữ ở các quãng im -
đúng cách tôi đã kết luận nhầm rằng câu đệm hỏng. Nên ở đây:

  - CHỈ phiên âm các đoạn CÓ TIẾNG, không đưa cả file (gồm quãng im) vào STT.
  - In kèm mức của từng đoạn để người đọc biết đoạn nào đáng tin.

    .venv\\python.exe scripts\\tach_kenh_nghiem_thu.py
    .venv\\python.exe scripts\\tach_kenh_nghiem_thu.py --phien 99ee5360 --nghe
"""
import argparse
import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DU_AN = Path(__file__).resolve().parent.parent
RA = DU_AN / "data" / "tach_kenh"
STT_URL = "http://127.0.0.1:8178/inference"

# Ngưỡng "có tiếng" trên thang int16. Nền của đường thoại đo được 11-35, nên 60
# đủ tách tiếng khỏi nền mà không cắt mất âm nhỏ.
NGUONG_INT16 = 60.0
# Gộp hai đoạn cách nhau dưới mức này thành một - nếu không thì mỗi từ thành một
# đoạn và STT nghe từng từ rời sẽ tệ hơn hẳn nghe cả câu.
NOI_NEU_CACH_MS = 400
# Đoạn ngắn hơn mức này là tiếng vọng hoặc nhiễu xung, không phải lời nói.
TOI_THIEU_MS = 250


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^a-z0-9 ]", " ", s)


def _tu(s: str) -> list[str]:
    return _bo_dau(s).split()


def khoang_cach(a: list[str], b: list[str]) -> int:
    """Levenshtein trên TỪ. Tự viết để khỏi thêm phụ thuộc chỉ vì một hàm."""
    truoc = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nay = [i]
        for j, y in enumerate(b, 1):
            nay.append(min(truoc[j] + 1, nay[j - 1] + 1, truoc[j - 1] + (x != y)))
        truoc = nay
    return truoc[-1]


def doan_co_tieng(x: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """Các đoạn có tiếng, trả (mẫu đầu, mẫu cuối)."""
    buoc = max(1, sr // 100)                       # cửa sổ 10ms
    n = len(x) // buoc
    manh = np.array([np.sqrt((x[i * buoc:(i + 1) * buoc] ** 2).mean()) * 32768
                     for i in range(n)])
    co = manh > NGUONG_INT16
    doan, dang, dau = [], False, 0
    for i, c in enumerate(co):
        if c and not dang:
            dang, dau = True, i
        elif not c and dang:
            dang = False
            doan.append((dau * buoc, i * buoc))
    if dang:
        doan.append((dau * buoc, len(x)))
    # nối các đoạn gần nhau
    gop: list[list[int]] = []
    for a, b in doan:
        if gop and a - gop[-1][1] < NOI_NEU_CACH_MS * sr // 1000:
            gop[-1][1] = b
        else:
            gop.append([a, b])
    return [(a, b) for a, b in gop if (b - a) * 1000 // sr >= TOI_THIEU_MS]


def stt(x: np.ndarray, sr: int, tam: Path) -> str:
    # Chuẩn đỉnh cho STT nghe được. An toàn ở đây vì ta chỉ đưa ĐOẠN CÓ TIẾNG -
    # không có quãng im nào để nó bịa chữ vào.
    y = x / (np.abs(x).max() + 1e-9) * 0.7
    sf.write(tam, y, sr)
    with open(tam, "rb") as f:
        r = requests.post(STT_URL, files={"file": (tam.name, f, "audio/wav")},
                          data={"language": "vi", "response_format": "json",
                                "temperature": "0"}, timeout=600)
    return (r.json().get("text") or "").strip()


def loi_ai(sid: str) -> str:
    """Chữ mà AI ĐÁNG LẼ đọc, lấy từ lịch sử hội thoại trong CSDL."""
    db = DU_AN / "data" / "app.db"
    if not db.exists():
        return ""
    cx = sqlite3.connect(db)
    dong = cx.execute(
        "SELECT content FROM conversation_turns WHERE session_id=? AND role='assistant'"
        " ORDER BY turn_index", (sid,)).fetchall()
    return " ".join(d[0] for d in dong if d[0])


def xu_ly(tep: Path, nghe: bool) -> dict:
    sid = tep.stem
    x, sr = sf.read(tep, dtype="float32")
    if x.ndim == 1:
        print(f"  {sid}: chỉ MỘT kênh, không tách được"); return {}
    khach, ai = x[:, 0], x[:, 1]
    RA.mkdir(parents=True, exist_ok=True)
    duong = {}
    for ten, ch in (("khach", khach), ("ai", ai)):
        p = RA / f"{sid}_{ten}.wav"
        sf.write(p, ch, sr)
        duong[ten] = p
    dbfs = lambda v: 20 * np.log10(np.sqrt((v ** 2).mean()) + 1e-12)
    print(f"\n=== {sid}  ({len(x)/sr:.1f}s @ {sr}Hz)")
    print(f"  khách: đỉnh {np.abs(khach).max():.3f}  {dbfs(khach):6.1f} dBFS")
    print(f"  AI   : đỉnh {np.abs(ai).max():.3f}  {dbfs(ai):6.1f} dBFS")
    print(f"  đã ghi {duong['khach'].name} và {duong['ai'].name}")

    kq = {"sid": sid, "duong": duong}
    if not nghe:
        return kq

    doan = doan_co_tieng(ai, sr)
    print(f"  kênh AI: {len(doan)} đoạn có tiếng")
    nghe_duoc = []
    tam = RA / "_tam.wav"
    for i, (a, b) in enumerate(doan, 1):
        chu = stt(ai[a:b], sr, tam)
        muc = dbfs(ai[a:b])
        print(f"    [{a/sr:5.1f}-{b/sr:5.1f}s {muc:6.1f} dBFS] {chu!r}")
        nghe_duoc.append(chu)
    if tam.exists():
        tam.unlink()

    goc = loi_ai(sid)
    if goc:
        a, b = _tu(goc), _tu(" ".join(nghe_duoc))
        d = khoang_cach(a, b)
        ty = d / max(1, len(a))
        print(f"\n  ĐỐI CHIẾU với lịch sử hội thoại ({len(a)} từ):")
        print(f"    lệch {d} từ  ->  sai {ty*100:.1f}%")
        kq["sai_tu"] = ty
    else:
        print("\n  (không có lịch sử hội thoại trong CSDL để đối chiếu)")
    return kq


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phien", nargs="*", default=[],
                    help="mã phiên; bỏ trống = 3 bản ghi mới nhất")
    ap.add_argument("--nghe", action="store_true",
                    help="cho STT nghe lại kênh AI và đối chiếu lịch sử")
    a = ap.parse_args()

    goc = DU_AN / "data" / "recordings"
    tep = sorted(goc.rglob("*.opus"), key=lambda p: p.stat().st_mtime, reverse=True)
    if a.phien:
        tep = [t for t in tep if t.stem in a.phien]
    else:
        tep = tep[:3]
    if not tep:
        print("không thấy bản ghi nào"); return 1
    for t in tep:
        xu_ly(t, a.nghe)
    print(f"\nFile tách nằm ở {RA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
