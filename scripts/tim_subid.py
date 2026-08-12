"""Tìm mã thuê bao (subId) của SIM đang có, để đặt làm SIM gọi mặc định."""
import re, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=True, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("BẢNG THUÊ BAO (content://telephony/siminfo)")
out = sh("content query --uri content://telephony/siminfo "
         "--projection _id:sim_id:display_name:carrier_name:number")
for l in out.splitlines():
    if "Row:" in l:
        print(f"  {l.strip()[:150]}")
if "Row:" not in out:
    print(f"  {out[:200]}")

print("\nSIM MẶC ĐỊNH HIỆN TẠI")
for k, ten in (("multi_sim_voice_call", "gọi thoại"),
               ("multi_sim_data_call", "dữ liệu"),
               ("multi_sim_sms", "tin nhắn")):
    print(f"  {ten:<12} = {sh(f'settings get global {k}', root=False)}")

print("\nTHUÊ BAO ĐANG HOẠT ĐỘNG (lọc từ dumpsys isub)")
d = sh("dumpsys isub")
# chỉ lấy các dòng mô tả thuê bao, bỏ log getPhoneId
for l in d.splitlines():
    if re.search(r"SubscriptionInfo|mSubId|simSlotIndex=\d", l) and "getPhoneId" not in l:
        s = l.strip()
        if len(s) < 250:
            print(f"  {s[:230]}")
