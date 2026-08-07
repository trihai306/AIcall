"""Gọi qua ĐÚNG đường của hệ thống thật, không qua script gọi thử.

Vì sao cần script riêng: `goi_va_noi.py` tự nạp model, tự dựng cầu tiếng, tự
quay số - tiện để thử nhưng KHÔNG phải đường mà sản phẩm chạy. Đường thật là

    POST /api/phones/contacts/{id}/call
      -> _dial_contact  -> mo_phien + dialer_service.dial
                        -> PhoneCallManager.start (cầu tiếng + tiêm + canh)

Hai đường từng lệch nhau ở `src` (3 với 4) và ở chỗ có canh đường tiêm hay không,
nên sửa xong ở script mà không thử lại đường này là chưa chắc đã xong.

Script tạo/tìm số trong danh bạ rồi bấm gọi qua API, sau đó theo dõi phiên: nghe
được gì, trả lời gì, mấy lượt.

    python scripts/goi_qua_he_thong.py 0396130621
    python scripts/goi_qua_he_thong.py 0396130621 --giay 60 --giong giong_nam
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "http://127.0.0.1:8100"


def api(duong: str, du_lieu=None, cho: int = 120):
    req = urllib.request.Request(
        API + duong,
        data=json.dumps(du_lieu, ensure_ascii=False).encode() if du_lieu is not None else None,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST" if du_lieu is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=cho) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("so")
    ap.add_argument("--giay", type=int, default=60)
    ap.add_argument("--giong", default="default")
    ap.add_argument("--san-pham", default="vay tín chấp")
    a = ap.parse_args()

    dsach = api("/api/phones/contacts?limit=200").get("contacts", [])
    lien_he = next((c for c in dsach if c["phone"].strip() == a.so), None)
    if lien_he is None:
        print(f"  chưa có số {a.so} trong danh bạ, thêm mới ...")
        ra = api("/api/phones/contacts",
                 {"name": "Khách thử", "phone": a.so, "product": a.san_pham})
        if "error" in ra:
            print(f"  không thêm được: {ra['error']}")
            return 1
        lien_he = ra.get("contact") or ra
    cid = lien_he["contact_id"]
    print(f"  số {a.so} -> {cid} ({lien_he.get('name')})")

    print(f"  bấm gọi qua API, giọng '{a.giong}' ...")
    ra = api(f"/api/phones/contacts/{cid}/call", {"voice_name": a.giong})
    if ra.get("error"):
        print(f"  LỖI: {ra['error']}")
        return 1
    sid = ra.get("session_id") or (ra.get("session") or {}).get("session_id", "")
    print(f"  quay số: {ra.get('dialed')} | tiếng: {ra.get('tieng')} "
          f"{ra.get('canh_bao') or ''}")
    print(f"  phiên: {sid}\n")
    print("  >>> BẮT MÁY, NGHE LỜI CHÀO RỒI NÓI THỬ MỘT CÂU <<<\n")

    luot_da_in = 0
    t0 = time.time()
    while time.time() - t0 < a.giay:
        time.sleep(3)
        tt = api("/api/phones/status") if False else api("/api/devices")
        phien = api(f"/api/sessions/{sid}").get("session", {}) if sid else {}
        lich_su = phien.get("history", [])
        for m in lich_su[luot_da_in:]:
            ai = "KHÁCH" if m.get("role") == "user" else "AI   "
            print(f"  {ai} | {m.get('content','')[:96]}")
        luot_da_in = len(lich_su)

    print(f"\n  hết {a.giay}s. Dừng đường tiếng ...")
    print(f"  {api(f'/api/phones/contacts/{cid}/result', {'status': 'done'})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
