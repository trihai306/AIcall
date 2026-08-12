"""Cho STT nghe lai tung file trong thu muc "Check giong" roi in ra chu no NGHE
DUOC, kem moc thoi gian tung doan.

Day la cach duy nhat bat duoc loi "mat chu / doc sai / de chu" - do pho hay bien
do deu mu voi loai loi nay (xem ghi chu am rac dau manh).

Chay TREN MAY WIN:
    set PYTHONIOENCODING=utf-8 && .venv\\python.exe scripts\\soat_check_giong.py
"""
import io
import json
import sys
import urllib.request
import uuid
import wave
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

STT = "http://127.0.0.1:8178/inference"
GOC = Path(r"C:\Users\Admin\Desktop\Check giọng")
DUOI = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def nghe_lai(p: Path) -> dict:
    """Goi PhoWhisper. Dung multipart tu ghep de khoi phu thuoc requests."""
    ranh = uuid.uuid4().hex
    than = io.BytesIO()
    def w(s):
        than.write(s if isinstance(s, bytes) else s.encode("utf-8"))
    w(f"--{ranh}\r\n")
    w(f'Content-Disposition: form-data; name="file"; filename="a{p.suffix}"\r\n')
    w("Content-Type: application/octet-stream\r\n\r\n")
    w(p.read_bytes()); w("\r\n")
    for k, v in (("language", "vi"), ("response_format", "verbose_json")):
        w(f"--{ranh}\r\n")
        w(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    w(f"--{ranh}--\r\n")
    req = urllib.request.Request(
        STT, data=than.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={ranh}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def dai_giay(p: Path):
    if p.suffix.lower() != ".wav":
        return None
    try:
        with wave.open(str(p)) as f:
            return f.getnframes() / f.getframerate()
    except Exception:
        return None


def main():
    if not GOC.exists():
        print("KHONG THAY:", GOC); return
    tep = sorted(x for x in GOC.rglob("*") if x.suffix.lower() in DUOI)
    print(f"{len(tep)} tep trong {GOC}\n")
    for p in tep:
        d = dai_giay(p)
        print("=" * 78)
        print(f"[{p.parent.name}] {p.name}")
        print(f"   dai: {d:.2f}s" if d else "   dai: (khong doc duoc)")
        try:
            r = nghe_lai(p)
        except Exception as e:
            print("   STT LOI:", e); continue
        if r.get("error"):
            print("   STT LOI:", r["error"]); continue
        print(f"   NGHE RA: {r.get('text','').strip()}")
        for s in (r.get("segments") or []):
            b, k = s.get("start"), s.get("end")
            if b is None:
                continue
            print(f"      {b:6.2f}-{k:6.2f}s  {s.get('text','').strip()}")


if __name__ == "__main__":
    main()
