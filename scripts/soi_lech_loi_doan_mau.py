"""Đoạn mẫu có khớp lời của nó không? Cho STT nghe lại từng file WAV mẫu.

Vì sao cần: F5 canh chữ theo `ref_text` rồi sinh tiếp phần mới trên nền
`ref_audio`. Nếu WAV có chữ mà TXT không ghi, chỗ lệch đó không biến mất - nó
rò sang phần sinh, nghe ra như bị chèn thêm từ giữa câu. Đây là lỗi đã gặp
thật: đoạn mẫu lệch lời làm F5 đọc ra đúng chữ sai đó, 5/5 lượt, mọi nfe.

Xuất JSON UTF-8 chứ không in ra màn hình: chuỗi tiếng Việt qua PowerShell rồi
SSH bị hỏng dấu ở nhiều tầng, đọc bằng mắt trên console là truy nhầm.

Chạy TRÊN MÁY WIN:
    .venv\\python.exe scripts\\soi_lech_loi_doan_mau.py
    .venv\\python.exe scripts\\soi_lech_loi_doan_mau.py --giong giong_heu heu_a
"""
import argparse
import hashlib
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
KHO = Path(__file__).resolve().parents[1] / "models" / "tts" / "ref_voices"
RA = Path(__file__).resolve().parents[1] / "logs" / "lech_loi_doan_mau.json"


def gon(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[.,!?;:\"'()\[\]…-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(a: str, b: str) -> float:
    """Tỉ lệ ký tự sai giữa lời ghi và lời STT nghe được."""
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--giong", nargs="*", default=None,
                    help="Mặc định soi mọi giọng trong kho.")
    a = ap.parse_args()

    ten = a.giong or sorted(p.stem for p in KHO.glob("*.wav"))
    ket = []
    for t in ten:
        wav, txt = KHO / f"{t}.wav", KHO / f"{t}.txt"
        if not wav.exists() or not txt.exists():
            continue
        ghi = txt.read_text(encoding="utf-8").strip()
        x, sr = sf.read(wav)
        try:
            nghe = nghe_lai(wav)
        except Exception as e:
            nghe = f"<LOI STT: {e}>"
        ket.append({
            "giong": t,
            "md5_wav": hashlib.md5(wav.read_bytes()).hexdigest(),
            "giay": round(len(x) / sr, 2),
            "loi_ghi_trong_txt": ghi,
            "loi_STT_nghe_duoc": nghe,
            "cer": round(cer(ghi, nghe), 4),
            # "dạ" là chữ đang bị nghi rò sang phần sinh
            "txt_co_da": bool(re.search(r"\bdạ\b", ghi, re.I)),
            "wav_co_da": bool(re.search(r"\bdạ\b", nghe, re.I)),
        })

    RA.parent.mkdir(parents=True, exist_ok=True)
    RA.write_text(json.dumps(ket, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"xong {len(ket)} giong -> {RA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
