"""Đọc nhật ký cuộc gọi: có nối máy được không, bao lâu, vì sao dừng."""
import re, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("5 cuộc gọi gần nhất:")
# shell không có quyền READ_CALL_LOG -> phải chạy qua root.
# Bọc cả lệnh trong nháy đơn, không thì shell trên máy tách tham số sai.
out = sh('content query --uri content://call_log/calls '
         '--projection number:date:duration:type', root=True)
out = "\n".join(out.splitlines()[-5:])
LOAI = {"1": "gọi đến", "2": "gọi đi", "3": "nhỡ", "5": "bị từ chối", "6": "chặn"}
for l in out.splitlines()[:5]:
    so = re.search(r"number=([^,]*)", l)
    dt = re.search(r"date=(\d+)", l)
    du = re.search(r"duration=(\d+)", l)
    ty = re.search(r"type=(\d+)", l)
    if not dt:
        print(f"  {l[:120]}")
        continue
    khi = time.strftime("%H:%M:%S", time.localtime(int(dt.group(1)) / 1000))
    giay = int(du.group(1)) if du else 0
    print(f"  {khi}  {so.group(1) if so else '?':<14}"
          f" {LOAI.get(ty.group(1) if ty else '', '?'):<12} {giay}s"
          + ("   -> ĐÃ NỐI MÁY" if giay > 0 else "   -> không nối được"))

print("\nLý do kết thúc gần nhất (từ log telecom):")
lg = sh("logcat -d -t 600 | grep -i -E 'disconnect.*cause|DisconnectCause'")
thay = [l.strip()[-120:] for l in lg.splitlines()][-6:]
print("  " + ("\n  ".join(thay) if thay else "(không thấy)"))
