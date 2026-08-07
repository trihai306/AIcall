"""Windows có nhìn thấy điện thoại qua USB không? Tách bạch ba mức hỏng."""
import subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")

def ps(cmd):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=60)
    return (r.stdout or "").strip()

print("1) THIẾT BỊ USB WINDOWS ĐANG THẤY (lọc Samsung/Android/ADB)")
out = ps("Get-PnpDevice | Where-Object { $_.FriendlyName -match 'Samsung|Android|ADB|SAMSUNG_Android' } "
         "| Select-Object Status,Class,FriendlyName | Format-Table -AutoSize | Out-String -Width 200")
print(out if out.strip() else "   (không thấy thiết bị Samsung/Android nào)")

print("\n2) ADB THẤY GÌ")
r = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=30)
print("   " + "\n   ".join((r.stdout or "").strip().splitlines()))

print("\n3) CHẨN ĐOÁN")
co_usb = bool(out.strip())
co_adb = "device" in (r.stdout or "").replace("List of devices attached", "")
if not co_usb:
    print("   Windows KHÔNG thấy máy qua USB.")
    print("   -> Cáp rút, máy tắt nguồn, hoặc cáp chỉ có dây sạc không có dây dữ liệu.")
elif not co_adb:
    print("   Windows THẤY máy nhưng ADB thì không.")
    print("   -> Máy đang khoá màn hình, hoặc gỡ lỗi USB bị tắt/chưa cho phép.")
    print("      Mở khoá máy rồi chấp nhận hộp thoại 'Cho phép gỡ lỗi USB'.")
else:
    print("   Cả hai đều thấy - máy sẵn sàng.")
