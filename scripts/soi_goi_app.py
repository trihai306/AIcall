"""Soi ĐƯỜNG GỌI THẬT CỦA APP, ghi lại từng giây xem hỏng ở khâu nào.

Chạy song song hai việc:
  1. Bấm gọi qua ĐÚNG API mà nút "Gọi" của app dùng (POST /api/phones/contacts/{id}/call)
  2. Cứ 1 giây đọc: mForegroundCallState, dòng trạng thái trong dumpsys telecom,
     precise_call_state (hàm backend thật sự dùng), và các control đường tiêm.

Mục tiêu: tách ba khả năng
  A. precise_call_state KHÔNG BAO GIỜ = 1  -> chao_khi_bat_may không chạy tới
     phần đặt đường tiêm -> khách không nghe gì.
  B. Đặt được đường tiêm rồi bị HAL giật lại -> khách nghe được một nhịp rồi im.
  C. Đường tiêm đúng suốt -> lỗi nằm ở chỗ khác (tiếng không được đẩy xuống).

    python scripts/soi_goi_app.py 0396130621 --giay 45
"""

import argparse
import asyncio
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, r"C:\duan\chat-ai")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

API = "http://127.0.0.1:8100"
SERIAL = "21f10e44220c7ece"
CANH = ("ABOX UAIF0 SPK", "AIF1TX1 Input 2", "ABOX SPUS OUT0", "ABOX NSRC1")


def api(duong, du_lieu=None, cho=120):
    req = urllib.request.Request(
        API + duong,
        data=json.dumps(du_lieu, ensure_ascii=False).encode() if du_lieu is not None else None,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST" if du_lieu is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=cho) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def sh(*args, t=20.0):
    p = await asyncio.create_subprocess_exec(
        "adb", "-s", SERIAL, *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        o, e = await asyncio.wait_for(p.communicate(), timeout=t)
    except asyncio.TimeoutError:
        p.kill()
        return ""
    return (o or b"").decode("utf-8", "replace") + (e or b"").decode("utf-8", "replace")


async def theo_doi(t0, ket_qua, dung: asyncio.Event):
    """Đọc trạng thái mỗi giây. TOÀN LÀ THAO TÁC ĐỌC - không ghi mixer."""
    from backend.services import adb_service
    while not dung.is_set():
        t = round(time.perf_counter() - t0, 1)
        reg = await sh("shell", "dumpsys", "telephony.registry")
        m = re.search(r"mForegroundCallState=(\d+)", reg)
        fg = m.group(1) if m else "?"

        tele = await sh("shell", "dumpsys", "telecom")
        # bắt MỌI dòng có vẻ mang trạng thái cuộc gọi, không chỉ mẫu code đang tìm
        dong = [d.strip()[:150] for d in tele.splitlines()
                if re.search(r"state\s*[=:]\s*\w+", d, re.I) or "[Call id" in d]
        khop_code = ("STATE=ACTIVE" in tele.upper() or "STATE: ACTIVE" in tele.upper())

        ma, mo_ta = await adb_service.precise_call_state(SERIAL)
        tiem = await adb_service.doc_duong_tiem(SERIAL)
        tt = {k: tiem.get(k) for k in CANH}

        ket_qua.append({"t": t, "fg": fg, "precise": ma, "mo_ta": mo_ta,
                        "telecom_khop_ACTIVE": khop_code,
                        "telecom_dong": dong[:4], "tiem": tt})
        print(f"  {t:5.1f}s | fg={fg} | precise={ma} ({mo_ta[:34]}) | "
              f"telecom_ACTIVE={khop_code} | UAIF0={tt['ABOX UAIF0 SPK']} "
              f"TX1In2={tt['AIF1TX1 Input 2']} SPUS0={tt['ABOX SPUS OUT0']}")
        if dong:
            print(f"          telecom: {dong[0]}")
        await asyncio.sleep(1.0)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=45)
    ap.add_argument("--giong", default="default")
    a = ap.parse_args()

    ds = api("/api/phones/contacts?limit=200").get("contacts", [])
    lh = next((c for c in ds if c["phone"].strip() == a.so), None)
    if lh is None:
        ra = api("/api/phones/contacts",
                 {"name": "Khách thử", "phone": a.so, "product": "vay tín chấp"})
        if "error" in ra:
            print("khong them duoc lien he:", ra["error"])
            return 1
        lh = ra.get("contact") or ra
    cid = lh["contact_id"]

    t0 = time.perf_counter()
    ket_qua = []
    dung = asyncio.Event()
    doi = asyncio.create_task(theo_doi(t0, ket_qua, dung))

    print(f"\n[BAM GOI QUA API — dung duong cua nut 'Goi' trong app]")
    ra = api(f"/api/phones/contacts/{cid}/call", {"voice_name": a.giong})
    print(f"  dialed={ra.get('dialed')} duong_tieng={ra.get('duong_tieng')} "
          f"canh_bao={ra.get('canh_bao')!r} detail={ra.get('detail')!r}")
    sid = ra.get("session_id", "")
    print(f"  phien={sid}")
    print("\n  >>> BAT MAY VA NGHE. Noi mot cau bat ky. <<<\n")

    await asyncio.sleep(a.giay)
    dung.set()
    await doi

    print("\n=== TOM TAT ===")
    dat_duoc = [r for r in ket_qua if r["tiem"]["ABOX UAIF0 SPK"] == "SIFS1"]
    noi_may = [r for r in ket_qua if r["precise"] == 1]
    fg1 = [r for r in ket_qua if r["fg"] == "1"]
    print(f"  mForegroundCallState len 1        : "
          f"{('CO, luc ' + str(fg1[0]['t']) + 's') if fg1 else 'KHONG BAO GIO'}")
    print(f"  precise_call_state tra ve 1       : "
          f"{('CO, luc ' + str(noi_may[0]['t']) + 's') if noi_may else 'KHONG BAO GIO'}")
    print(f"  duong tiem (UAIF0 SPK=SIFS1)      : "
          f"{('DAT DUOC luc ' + str(dat_duoc[0]['t']) + 's, giu duoc ' + str(len(dat_duoc)) + '/' + str(len(ket_qua)) + ' lan doc') if dat_duoc else 'KHONG BAO GIO DAT DUOC'}")
    phien = api(f"/api/sessions/{sid}").get("session", {}) if sid else {}
    print(f"  luot hoi thoai                    : {len(phien.get('history', []))}")
    for m in phien.get("history", [])[:6]:
        print(f"     {m.get('role'):9} | {m.get('content','')[:80]}")

    with open(r"C:\duan\chat-ai\logs\soi_goi_app.json", "w", encoding="utf-8") as f:
        json.dump(ket_qua, f, ensure_ascii=False, indent=1)
    print("\n  chi tiet: logs\\soi_goi_app.json")
    api(f"/api/phones/contacts/{cid}/result", {"status": "done"})
    return 0


raise SystemExit(asyncio.run(main()))
