"""Tiếng F5 sinh ra có bị chen thêm chữ so với câu yêu cầu không?

Người dùng báo: giọng heu "đang nói bị chen từ dạ vào". Câu thử vốn ĐÃ có
"Dạ" ở đầu 3 câu, nên phải đếm chứ không nghe cảm tính - nếu mọi giọng đều ra
đúng 3 lần thì đó là câu thử chứ không phải lỗi; nếu riêng heu ra nhiều hơn
thì mới là F5 chen thêm.

Xuất JSON UTF-8, không in tiếng Việt ra console (qua SSH là hỏng dấu).

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\soi_da_chen_them.py --thu-muc data\\thu_giong
"""
import argparse
import io
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import soundfile as sf  # noqa: E402

STT = "http://127.0.0.1:8178/inference"
GOC = Path(__file__).resolve().parents[1]


def gon(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(a: str, b: str) -> float:
    a, b = gon(a), gon(b)
    if not a:
        return 0.0
    truoc = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        sau = [i]
        for j, cb in enumerate(b, 1):
            sau.append(min(truoc[j] + 1, sau[j - 1] + 1,
                           truoc[j - 1] + (ca != cb)))
        truoc = sau
    return truoc[-1] / len(a)


def nghe_lai(p: Path) -> str:
    x, sr = sf.read(p)
    b = io.BytesIO()
    sf.write(b, x, sr, format="WAV", subtype="PCM_16")
    bd = b"----x"
    body = (b"--" + bd + b"\r\nContent-Disposition: form-data; name=\"file\"; "
            b"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
            + b.getvalue() + b"\r\n--" + bd + b"--\r\n")
    r = urllib.request.Request(
        STT, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=----x"})
    return json.loads(urllib.request.urlopen(r, timeout=300).read()).get("text", "").strip()


def dem_da(s: str) -> int:
    return len(re.findall(r"\bdạ\b", gon(s)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thu-muc", default="data/thu_giong")
    ap.add_argument("--cau-tep", default="data/cau_thu_ba_truc.txt")
    ap.add_argument("--ra", default="logs/da_chen_them.json")
    a = ap.parse_args()

    mong_doi = (GOC / a.cau_tep).read_text(encoding="utf-8").strip()
    can_co = dem_da(mong_doi)

    tm = GOC / a.thu_muc
    # chỉ lấy bản gốc 24kHz: bản 8k và qua_dien_thoai là cùng tiếng đó hạ chất
    tep = sorted(p for p in tm.glob("*.wav")
                 if not p.stem.endswith(("_8k", "_qua_dien_thoai")))

    ket = {"cau_yeu_cau": mong_doi, "so_da_can_co": can_co, "giong": []}
    for p in tep:
        try:
            nghe = nghe_lai(p)
        except Exception as e:
            nghe = f"<LOI STT: {e}>"
        ket["giong"].append({
            "ten": p.stem,
            "STT_nghe_duoc": nghe,
            "so_da_nghe_duoc": dem_da(nghe),
            "chen_them": dem_da(nghe) - can_co,
            "cer": round(cer(mong_doi, nghe), 4),
        })

    out = GOC / a.ra
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ket, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"xong {len(ket['giong'])} tep -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
