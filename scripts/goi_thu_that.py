"""Gọi một cuộc thật rồi đo codec thoại đang dùng.

Đây là phép đo duy nhất trả lời dứt điểm: cuộc gọi thật dùng AMR-NB 8kHz hay
AMR-WB 16kHz. Mọi thứ trước đó chỉ là mô phỏng bằng ffmpeg.
"""
import re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"
SO = "0396130621"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

def trang_thai_goi():
    d = sh("dumpsys telephony.registry")
    m = re.search(r"mCallState=(\d)", d)
    ten = {0: "rảnh", 1: "đang đổ chuông", 2: "đang trong cuộc gọi"}
    return int(m.group(1)) if m else -1, ten.get(int(m.group(1)) if m else -1, "?")

print(f"Trạng thái trước khi gọi: {trang_thai_goi()[1]}")
sh("input keyevent KEYCODE_WAKEUP")
time.sleep(1)

print(f"\nGọi tới {SO} ...")
out = sh(f"am start -a android.intent.action.CALL -d tel:{SO}")
print("  " + (out.splitlines()[0] if out else "(đã gửi lệnh)"))

print("\nTheo dõi trạng thái cuộc gọi:")
codec_thay = set()
for i in range(40):                       # tối đa 80 giây
    time.sleep(2)
    ma, ten = trang_thai_goi()
    # bắt thông tin codec trong log âm thanh khi đã kết nối
    if ma == 2:
        lg = sh("logcat -d -t 300 | grep -i -E 'amr|codec|wideband|nb_wb|voice.*rate'")
        for l in lg.splitlines():
            if re.search(r"amr[-_]?(nb|wb)|wideband|narrowband", l, re.I):
                codec_thay.add(l.strip()[-110:])
    if i % 3 == 0 or ma == 2:
        print(f"  {i*2:>3}s: {ten}")
    if ma == 2 and i > 6:
        break
    if ma == 0 and i > 10:
        print("  -> cuộc gọi đã kết thúc hoặc không kết nối được")
        break

ma, ten = trang_thai_goi()
print(f"\nTrạng thái cuối: {ten}")

if codec_thay:
    print("\nDẤU VẾT CODEC TRONG LOG:")
    for c in sorted(codec_thay)[:10]:
        print(f"  {c}")
else:
    print("\nKhông thấy dấu vết codec trong logcat.")

print("\nTHÔNG TIN MẠNG LÚC GỌI:")
print(f"  loại mạng      : {sh('getprop gsm.network.type')}")
d = sh("dumpsys telephony.registry")
for l in d.splitlines():
    if "getRilVoiceRadioTechnology" in l:
        m = re.search(r"getRilVoiceRadioTechnology=\d+\((\w+)\)", l)
        if m:
            print(f"  sóng thoại     : {m.group(1)}")
        break
print(f"  IMS đăng ký    : {'CÓ' if 'mImsRegistered=true' in d else 'CHƯA'}")

print("\nCHẾ ĐỘ ÂM THANH:")
au = sh("dumpsys audio | grep -m4 -i -E 'mode|call'")
print("  " + (au.replace("\n", "\n  ")[:400] if au else "(không đọc được)"))
