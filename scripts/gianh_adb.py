"""Dừng mọi máy chủ adb rồi khởi động lại bằng adb của dự án.

Máy có hai adb: platform-tools (của ta) và của phần mềm phone farm xiaowei.
Cả hai dùng chung cổng 5037, ai chạy trước thì làm chủ. Khi xiaowei làm chủ,
`adb devices` của ta trả về rỗng dù Windows nhận thiết bị hoàn toàn khoẻ.
"""
import subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8")
import psutil

print("Các tiến trình adb trước khi dọn:")
for p in psutil.process_iter(["name", "exe"]):
    if (p.info.get("name") or "").lower() == "adb.exe":
        print(f"  PID {p.pid:<7} {p.info.get('exe')}")

n = 0
for p in psutil.process_iter(["name"]):
    if (p.info.get("name") or "").lower() == "adb.exe":
        try:
            p.kill(); n += 1
        except Exception as e:
            print(f"  không dừng được {p.pid}: {e}")
print(f"\nĐã dừng {n} tiến trình adb")
time.sleep(3)

ADB = r"C:\platform-tools\adb.exe"
subprocess.run([ADB, "start-server"], capture_output=True, timeout=60)
time.sleep(4)
r = subprocess.run([ADB, "devices", "-l"], capture_output=True, text=True, timeout=30)
print("\nSau khi khởi động lại bằng platform-tools:")
print("  " + (r.stdout or "").strip().replace("\n", "\n  "))

print("\nadb nào đang giữ cổng 5037 bây giờ:")
for p in psutil.process_iter(["name", "exe"]):
    if (p.info.get("name") or "").lower() == "adb.exe":
        print(f"  PID {p.pid:<7} {p.info.get('exe')}")
