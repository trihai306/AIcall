#!/usr/bin/env python3
"""May chu nho phuc vu file audio test de nghe tren dien thoai.

Chay doc lap, KHONG dinh vao backend, vi backend hay khoi dong lai.
Nghe tren moi duong mang nen vao duoc ca qua Tailscale lan Wi-Fi nha.

    python3 scripts/may_chu_nghe.py            # cong 8123, thu muc nghe/
    python3 scripts/may_chu_nghe.py --cong 9000 --thu-muc /duong/khac
"""

from __future__ import annotations

import argparse
import contextlib
import html
import ipaddress
import json
import socket
import subprocess
import wave
from datetime import datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

DUOI_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
KIEU_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}
GOC_DU_AN = Path(__file__).resolve().parent.parent


def do_dai_giay(tep: Path) -> float | None:
    """Doc thoi luong tu phan dau WAV. Dinh dang khac thi chiu, tra None."""
    if tep.suffix.lower() != ".wav":
        return None
    try:
        with contextlib.closing(wave.open(str(tep), "rb")) as w:
            khung = w.getnframes()
            tan_so = w.getframerate()
            return khung / tan_so if tan_so else None
    except (wave.Error, OSError):
        return None


def quet_thu_muc(thu_muc: Path) -> list[dict]:
    """Liet ke file audio, moi nhat truoc. Nhan lay tu file .txt cung ten."""
    if not thu_muc.is_dir():
        return []
    ket_qua = []
    for tep in thu_muc.iterdir():
        if not tep.is_file() or tep.suffix.lower() not in DUOI_AUDIO:
            continue
        ghi_chu = tep.with_suffix(tep.suffix + ".txt")
        nhan = ""
        if ghi_chu.is_file():
            with contextlib.suppress(OSError, UnicodeDecodeError):
                nhan = ghi_chu.read_text(encoding="utf-8").strip()
        thong_tin = tep.stat()
        ket_qua.append(
            {
                "ten": tep.name,
                "nhan": nhan,
                "sua_luc": thong_tin.st_mtime,
                "dung_luong": thong_tin.st_size,
                "giay": do_dai_giay(tep),
            }
        )
    ket_qua.sort(key=lambda m: m["sua_luc"], reverse=True)
    return ket_qua


def go_dung_luong(so_byte: int) -> str:
    if so_byte < 1024:
        return f"{so_byte} B"
    if so_byte < 1024 * 1024:
        return f"{so_byte / 1024:.0f} KB"
    return f"{so_byte / 1024 / 1024:.1f} MB"


def go_thoi_luong(giay: float | None) -> str:
    if giay is None:
        return ""
    phut, con_lai = divmod(int(round(giay)), 60)
    return f"{phut}:{con_lai:02d}" if phut else f"{giay:.1f}s"


TRANG = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0f1115">
<title>Nghe thu</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0 0 3rem;
    background: #0f1115; color: #e8eaed;
    font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    -webkit-text-size-adjust: 100%;
  }}
  header {{
    position: sticky; top: 0; z-index: 5;
    padding: max(1rem, env(safe-area-inset-top)) 1rem .75rem;
    background: rgba(15,17,21,.92); backdrop-filter: blur(12px);
    border-bottom: 1px solid #23262e;
  }}
  h1 {{ margin: 0; font-size: 1.05rem; font-weight: 600; letter-spacing: .01em; }}
  .phu {{ margin-top: .15rem; font-size: .8rem; color: #8b919c; }}
  main {{ padding: .75rem 1rem; display: flex; flex-direction: column; gap: .6rem; }}
  .the {{
    background: #171a20; border: 1px solid #23262e; border-radius: 14px;
    padding: .85rem .9rem;
  }}
  .the.dau {{ border-color: #2f6b4f; }}
  .nhan {{ font-weight: 600; font-size: .98rem; margin-bottom: .1rem; word-break: break-word; }}
  .meta {{
    font-size: .74rem; color: #8b919c; font-variant-numeric: tabular-nums;
    display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: .6rem;
  }}
  .moi {{ color: #6ee7a8; }}
  audio {{ width: 100%; height: 40px; display: block; }}
  .trong {{ padding: 3rem 1rem; text-align: center; color: #6c727d; }}
  #bao {{
    position: fixed; left: 50%; transform: translateX(-50%);
    bottom: max(1.1rem, env(safe-area-inset-bottom));
    background: #2f6b4f; color: #fff; border: 0;
    padding: .7rem 1.2rem; border-radius: 999px;
    font: inherit; font-weight: 600; font-size: .9rem;
    box-shadow: 0 6px 20px rgba(0,0,0,.5); display: none;
  }}
</style>
</head>
<body>
<header>
  <h1>Nghe thu</h1>
  <div class="phu">{tom_tat}</div>
</header>
<main>{danh_sach}</main>
<button id="bao" onclick="location.reload()">Co file moi — tai lai</button>
<script>
// Khong tu tai lai trang: dang nghe ma trang nhay lai la dut tieng.
// Chi hien nut de nguoi dung tu bam khi da nghe xong.
const banDau = {chu_ky};
setInterval(async () => {{
  try {{
    const r = await fetch('/api/danh_sach', {{ cache: 'no-store' }});
    const d = await r.json();
    if (d.chu_ky !== banDau) document.getElementById('bao').style.display = 'block';
  }} catch (e) {{ /* mat mang thi thoi, lat nua thu lai */ }}
}}, 5000);
</script>
</body>
</html>"""


def dung_trang(muc: list[dict]) -> str:
    if muc:
        tom_tat = f"{len(muc)} file · moi nhat {datetime.fromtimestamp(muc[0]['sua_luc']):%H:%M %d/%m}"
    else:
        tom_tat = "chua co file nao"

    khoi = []
    for i, m in enumerate(muc):
        ten_an = html.escape(m["ten"])
        nhan = html.escape(m["nhan"]) if m["nhan"] else ten_an
        luc = datetime.fromtimestamp(m["sua_luc"])
        meta = [
            f"<span{' class=\"moi\"' if i == 0 else ''}>{luc:%H:%M %d/%m}</span>",
            f"<span>{go_dung_luong(m['dung_luong'])}</span>",
        ]
        if thoi_luong := go_thoi_luong(m["giay"]):
            meta.insert(1, f"<span>{thoi_luong}</span>")
        if m["nhan"]:
            meta.append(f"<span>{ten_an}</span>")
        khoi.append(
            f'<div class="the{" dau" if i == 0 else ""}">'
            f'<div class="nhan">{nhan}</div>'
            f'<div class="meta">{"".join(meta)}</div>'
            f'<audio controls preload="none" src="/tep/{ten_an}"></audio>'
            f"</div>"
        )
    danh_sach = "".join(khoi) or '<div class="trong">Chua co file nao trong thu muc nghe/</div>'
    return TRANG.format(tom_tat=html.escape(tom_tat), danh_sach=danh_sach, chu_ky=json.dumps(chu_ky(muc)))


def chu_ky(muc: list[dict]) -> str:
    """Dau van tay cua danh sach - doi la biet co file moi."""
    return "|".join(f"{m['ten']}:{m['sua_luc']:.0f}" for m in muc)


class Xu(BaseHTTPRequestHandler):
    server_version = "MayChuNghe/1.0"

    def __init__(self, *a, thu_muc: Path, **kw):
        self.thu_muc = thu_muc
        super().__init__(*a, **kw)

    def log_message(self, dinh_dang, *doi_so):  # bot rac ra man hinh
        pass

    def do_GET(self):
        duong = unquote(urlparse(self.path).path)
        if duong == "/":
            return self._tra_chu(dung_trang(quet_thu_muc(self.thu_muc)), "text/html; charset=utf-8")
        if duong == "/api/danh_sach":
            muc = quet_thu_muc(self.thu_muc)
            than = json.dumps({"chu_ky": chu_ky(muc), "so_luong": len(muc)})
            return self._tra_chu(than, "application/json")
        if duong.startswith("/tep/"):
            return self._tra_tep(duong[len("/tep/") :])
        if duong == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)

    def _tra_chu(self, than: str, kieu: str):
        du_lieu = than.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", kieu)
        self.send_header("Content-Length", str(len(du_lieu)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(du_lieu)

    def _tra_tep(self, ten: str):
        # Chan moi muu do thoat ra ngoai thu muc (../, duong tuyet doi).
        tep = (self.thu_muc / ten).resolve()
        if self.thu_muc.resolve() not in tep.parents or not tep.is_file():
            return self.send_error(404)
        if tep.suffix.lower() not in DUOI_AUDIO:
            return self.send_error(403)

        co = tep.stat().st_size
        kieu = KIEU_MIME.get(tep.suffix.lower(), "application/octet-stream")
        # Safari tren iOS doi Range moi chiu phat; thieu la im ru.
        pham_vi = self.headers.get("Range", "")
        dau, cuoi = 0, co - 1
        ma = 200
        if pham_vi.startswith("bytes="):
            phan = pham_vi[6:].split("-")
            with contextlib.suppress(ValueError):
                dau = int(phan[0]) if phan[0] else 0
                cuoi = int(phan[1]) if len(phan) > 1 and phan[1] else co - 1
                ma = 206
        cuoi = min(cuoi, co - 1)
        dai = max(0, cuoi - dau + 1)

        self.send_response(ma)
        self.send_header("Content-Type", kieu)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(dai))
        if ma == 206:
            self.send_header("Content-Range", f"bytes {dau}-{cuoi}/{co}")
        self.end_headers()
        with tep.open("rb") as f:
            f.seek(dau)
            self.wfile.write(f.read(dai))


def dia_chi_tailscale() -> str | None:
    """Doc dia chi Tailscale tu card mang, khong goi CLI.

    Chay duoi launchd thi Tailscale CLI bao loi vi thieu ngu canh GUI, con
    dia chi tren card mang thi luc nao cung doc duoc. Tailscale cap dia chi
    trong dai 100.64.0.0/10 nen chi can do dung dai la ra.
    """
    dai_tailscale = ipaddress.ip_network("100.64.0.0/10")
    try:
        ra = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    for dong in ra.stdout.splitlines():
        phan = dong.split()
        if len(phan) >= 2 and phan[0] == "inet":
            with contextlib.suppress(ValueError):
                if ipaddress.ip_address(phan[1]) in dai_tailscale:
                    return phan[1]
    return None


def dia_chi_lan() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # khong gui goi nao, chi de hoi he dieu hanh
            return s.getsockname()[0]
    except OSError:
        return None


def main() -> None:
    p = argparse.ArgumentParser(description="May chu nghe file audio test tren dien thoai")
    p.add_argument("--cong", type=int, default=8123)
    p.add_argument("--thu-muc", default=str(GOC_DU_AN / "nghe"))
    tham_so = p.parse_args()

    thu_muc = Path(tham_so.thu_muc).expanduser().resolve()
    thu_muc.mkdir(parents=True, exist_ok=True)

    may = ThreadingHTTPServer(("0.0.0.0", tham_so.cong), partial(Xu, thu_muc=thu_muc))
    # flush=True: chay nen thi stdout bi dem, thieu no la log rong nhu chua chay.
    print(f"Thu muc : {thu_muc}", flush=True)
    for ten, dia_chi in (("Tailscale", dia_chi_tailscale()), ("Wi-Fi", dia_chi_lan())):
        if dia_chi:
            print(f"{ten:<10}: http://{dia_chi}:{tham_so.cong}", flush=True)
    try:
        may.serve_forever()
    except KeyboardInterrupt:
        may.shutdown()


if __name__ == "__main__":
    main()
