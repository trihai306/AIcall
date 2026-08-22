import json, sys, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
req=urllib.request.Request(
    "http://127.0.0.1:8100/api/phones/contacts/ct_b496cd7e/call",
    data=json.dumps({"voice_name":"giong_heu"}).encode(),
    headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=120) as r:
    d=json.load(r)
if d.get("error"): print("LỖI:", d["error"]); sys.exit()
c=d.get("contact",{})
print(f"số           : {c.get('phone')}  ({c.get('name') or 'không tên'})")
print(f"đã bấm số    : {d.get('dialed')}   máy: {(d.get('device') or {}).get('name')}")
print(f"đường tiếng  : {d.get('duong_tieng')}")
print(f"cảnh báo     : {d.get('canh_bao') or '(không có)'}")
print(f"chi tiết     : {d.get('detail') or '(không có)'}")
print(f"phiên AI     : {d.get('session_id')}")
