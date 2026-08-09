"""Vo hieu hoa F5TTS_REF_TEXT trong .env - gio da vo dung va la mot cai bay.

Tu 08-09 code lay loi doan mau tu tep `<giong>.txt` nam canh tep wav
(`_loi_doan_mau()`), khong lay tu .env nua. De lai mot gia tri CU trong .env chi
lam nguoi sau tuong no con tac dung, va lam backend in canh bao lech moi lan khoi
dong.

Vi sao lam bang BYTE chu khong doc thanh chuoi: `.env` cua du an nay tung bi
hong dau vi `Get-Content | Set-Content` cua PowerShell doc/ghi theo codepage
console. Doc-sua-ghi o muc byte thi moi dong khac giu nguyen tung byte mot, chi
dong minh dong den la doi.

Chay TREN MAY WIN:
    .venv\\python.exe scripts\\don_env_ref_text.py
    .venv\\python.exe scripts\\don_env_ref_text.py --thu   (chi xem, khong ghi)
"""
import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ENV = Path(".env")
KHOA = b"F5TTS_REF_TEXT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thu", action="store_true", help="chi in ra, khong ghi")
    a = ap.parse_args()

    if not ENV.exists():
        print(f"  khong thay {ENV.resolve()}")
        return 1

    goc = ENV.read_bytes()
    dong = goc.split(b"\n")
    doi, ra = 0, []
    for d in dong:
        if d.lstrip().startswith(KHOA):
            ra.append(b"# " + d.rstrip(b"\r"))
            ra.append(
                b"#   ^ da vo hieu 2026-08-09. Loi doan mau nay gio doc tu"
                b" models/tts/ref_voices/<giong>.txt")
            ra.append(
                b"#     Giu lai gia tri cu o day chi de doi chieu; sua no KHONG"
                b" con tac dung gi.")
            doi += 1
        else:
            ra.append(d)

    if doi == 0:
        print("  .env khong co F5TTS_REF_TEXT dang hoat dong - khong phai lam gi")
        return 0

    moi = b"\n".join(ra)
    print(f"  tim thay {doi} dong F5TTS_REF_TEXT, se chu thich lai")
    if a.thu:
        print("  (--thu: khong ghi gi ca)")
        return 0

    # KHONG dung with_suffix: ten tep la ".env" nen Path coi ".env" la phan
    # duoi, ket qua ra ".env.env.bak-...". Ghep thang vao ten cho chac.
    bak = ENV.with_name(f"{ENV.name}.bak-{date.today():%Y%m%d}")
    shutil.copy2(ENV, bak)
    ENV.write_bytes(moi)
    print(f"  da ghi. Ban cu: {bak.name}")
    print("  Khoi dong lai backend de an: start_services.ps1 -Detached -Restart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
