"""Kiểm cả chuỗi kết nối: máy tính -> USB -> điện thoại -> SIM, và các dịch vụ.

Chạy trước mỗi phiên làm việc để biết ngay khâu nào đứt, thay vì phát hiện giữa
một cuộc gọi thử.

    python scripts/kiem_toan_bo.py
"""

import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
SERIAL = "21f10e44220c7ece"


def chay(*a, t=60) -> str:
    r = subprocess.run(a, capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()


def sh(c: str, t: int = 60) -> str:
    return chay("adb", "-s", SERIAL, "shell", c, t=t)


def muc(ten: str, ok: bool, chi_tiet: str = "") -> bool:
    print(f"    {'OK   ' if ok else 'HỎNG '}{ten:<26}{chi_tiet[:70]}")
    return ok


def main() -> int:
    import httpx
    from backend.config import settings

    print("=== Chuỗi kết nối ===")
    ds = chay("adb", "devices")
    co_may = bool(re.search(rf"{SERIAL}\s+device\b", ds))
    tot = muc("điện thoại qua USB", co_may,
              SERIAL if co_may else "không thấy trong adb devices")
    if not co_may:
        print("\n    Cắm lại cáp USB, hoặc chạy scripts/gianh_adb.py nếu có adb khác giữ cổng.")
        return 1

    model = sh("getprop ro.product.model")
    tot &= muc("model", bool(model), model)

    sim = sh("getprop gsm.sim.state")
    khe = [k.strip().upper() for k in sim.split(",")]
    co_sim = any(k not in ("ABSENT", "UNKNOWN", "NOT_READY") for k in khe)
    tot &= muc("SIM", co_sim, f"{sim}  nhà mạng {sh('getprop gsm.operator.alpha')}")

    mang = sh("getprop gsm.network.type")
    tot &= muc("sóng", bool(mang and mang != "Unknown"), mang)

    root = sh("su -c id")
    tot &= muc("quyền root", "uid=0" in root, root[:50])

    mix = sh("su -c 'ls -l /data/local/tmp/mixctl'")
    tot &= muc("mixctl", "mixctl" in mix and "No such" not in mix, mix[:60])

    app = sh("pm path com.tuktech.voicebridge")
    tot &= muc("app cầu tiếng", "package:" in app, app[:60])

    quyen = sh("dumpsys package com.tuktech.voicebridge | grep CAPTURE_AUDIO_OUTPUT")
    tot &= muc("quyền thu cuộc gọi", "granted=true" in quyen,
               "CAPTURE_AUDIO_OUTPUT granted" if "granted=true" in quyen else quyen[:50])

    print("\n=== Dịch vụ trên máy tính ===")
    for ten, url in (("STT (PhoWhisper)", f"{settings.whisper_server_url}/health"),
                     ("LLM (Ollama)", "http://127.0.0.1:11434/api/tags")):
        try:
            r = httpx.get(url, timeout=5)
            tot &= muc(ten, r.status_code == 200, r.text[:60])
        except Exception as e:
            tot &= muc(ten, False, f"{type(e).__name__}: {str(e)[:50]}")

    print("\n=== Cấu hình đường tiếng ===")
    print(f"    đường tiêm      {settings.phone_duong_tiem}")
    print(f"    rate xuống/lên  {settings.phone_rate_xuong} / {settings.phone_rate_len} Hz")
    print(f"    đệm mồi         {settings.phone_dem_mo_ms} ms")
    print(f"    mức tiếng       {settings.phone_muc_dbfs} dBFS, đỉnh tối đa "
          f"{settings.phone_dinh_toi_da}")

    print("\n" + "=" * 62)
    print("SẴN SÀNG GỌI" if tot else "CÓ KHÂU ĐỨT - xem dòng HỎNG ở trên")
    print("=" * 62)
    return 0 if tot else 1


if __name__ == "__main__":
    raise SystemExit(main())
