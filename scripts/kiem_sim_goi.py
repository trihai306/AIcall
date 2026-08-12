"""SIM nào đang được chọn để GỌI ĐI? Khe 1 trống mà mặc định trỏ vào đó là gọi hỏng."""
import re, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("SIM MẶC ĐỊNH CHO TỪNG VIỆC")
for k, ten in (("multi_sim_voice_call", "gọi thoại"),
               ("multi_sim_data_call", "dữ liệu"),
               ("multi_sim_sms", "tin nhắn"),
               ("multi_sim_voice_prompt", "hỏi mỗi lần gọi")):
    print(f"  {ten:<20} = {sh(f'settings get global {k}')}")

print("\nCÁC THUÊ BAO ĐANG HOẠT ĐỘNG")
out = sh("dumpsys isub", root=True) or sh("dumpsys telephony.registry")
for l in out.splitlines():
    if re.search(r"subId|slotIndex|simSlotIndex|mDefaultVoiceSubId|defaultVoiceSubId", l, re.I):
        s = l.strip()
        if len(s) < 200:
            print(f"  {s}")

print("\nTHÔNG TIN THUÊ BAO (service call)")
# lấy subId đang dùng cho thoại
r = sh("service call isub 15")     # getDefaultVoiceSubId trên nhiều bản Android 9
print(f"  getDefaultVoiceSubId thô: {r[:120]}")

print("\nSỐ ĐIỆN THOẠI CỦA MÁY")
print(f"  {sh('service call iphonesubinfo 15')[:200] or '(không đọc được)'}")
