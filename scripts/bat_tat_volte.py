"""Tắt rồi bật lại nút VoLTE trong Cài đặt để ép hệ thống ghi và đăng ký lại."""
import re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

def ims():
    d = sh("dumpsys telephony.registry")
    return "mImsRegistered=true" in d

def toa_do_nut_volte():
    """Tìm toạ độ nút gạt của dòng 'VoLTE calls'."""
    sh("uiautomator dump /sdcard/ui.xml")
    xml = sh("cat /sdcard/ui.xml")
    # lấy khối chứa chữ VoLTE rồi tìm bounds của chính khối đó
    for m in re.finditer(r'<node[^>]*text="([^"]*VoLTE[^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
        x1, y1, x2, y2 = map(int, m.groups()[1:])
        return (x1 + x2) // 2, (y1 + y2) // 2, m.group(1)
    return None

print(f"IMS đăng ký lúc đầu: {'CÓ' if ims() else 'CHƯA'}")

vt = toa_do_nut_volte()
if not vt:
    print("Không tìm thấy dòng VoLTE trên màn hình - mở lại Cài đặt mạng")
    sh("am start -a android.settings.NETWORK_OPERATOR_SETTINGS")
    time.sleep(3)
    vt = toa_do_nut_volte()

if not vt:
    print("Vẫn không thấy. Dừng.")
    raise SystemExit(1)

x, y, ten = vt
print(f"Thấy '{ten}' ở ({x},{y})")

for lan, nhan in ((1, "TẮT"), (2, "BẬT lại")):
    sh(f"input tap {x} {y}")
    print(f"  chạm lần {lan} ({nhan})")
    time.sleep(4)

print("\nChờ IMS đăng ký (tối đa 90s) ...")
for i in range(18):
    time.sleep(5)
    if ims():
        print(f"  sau {(i+1)*5}s: ĐÃ ĐĂNG KÝ")
        break
    if (i + 1) % 6 == 0:
        print(f"  sau {(i+1)*5}s: chưa")
else:
    print("  hết 90s vẫn chưa")

print(f"\nKẾT QUẢ")
print(f"  IMS đăng ký      = {'CÓ' if ims() else 'CHƯA'}")
print(f"  volte_vt_enabled = {sh('settings get global volte_vt_enabled')}")
d = sh("dumpsys telephony.registry")
for l in d.splitlines():
    if "VoLteServiceState" in l:
        print(f"  {l.strip()}")
        break
cc = sh("dumpsys carrier_config | grep -m1 carrier_volte_available_bool")
print(f"  {cc.strip()}")
