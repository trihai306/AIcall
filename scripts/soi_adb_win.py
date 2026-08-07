"""Soi phía Windows: adb nào đang chạy, thiết bị ở trạng thái gì, ai giữ nó."""
import os, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")

def ps(cmd, width=220):
    r = subprocess.run(["powershell","-NoProfile","-Command",cmd],
                       capture_output=True, text=True, timeout=90)
    return (r.stdout or "").rstrip()

def sh(*a):
    try:
        r = subprocess.run(a, capture_output=True, text=True, timeout=60)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return f"(lỗi: {e})"

print("1) ĐANG DÙNG adb.exe NÀO")
print("   which:", ps("(Get-Command adb -EA SilentlyContinue).Source"))
print("   phiên bản:", sh("adb", "version").replace("\n", " | "))
print("   ANDROID_ADB_SERVER_PORT =", os.environ.get("ANDROID_ADB_SERVER_PORT", "(không đặt)"))
print("   các adb.exe trên máy:")
print(ps(r"Get-ChildItem -Path C:\ -Filter adb.exe -Recurse -EA SilentlyContinue -Force "
         r"| Select-Object -First 8 -ExpandProperty FullName") or "     (không tìm thấy thêm)")

print("\n2) TIẾN TRÌNH adb ĐANG CHẠY")
print(ps("Get-Process adb -EA SilentlyContinue | Select-Object Id,Path,StartTime "
         "| Format-Table -AutoSize | Out-String -Width 200") or "   (không có)")

print("\n3) CỔNG 5037 (máy chủ adb)")
print(ps("Get-NetTCPConnection -LocalPort 5037 -EA SilentlyContinue "
         "| Select-Object State,LocalAddress,OwningProcess | Format-Table -AutoSize | Out-String")
      or "   (không ai giữ 5037)")

print("\n4) THIẾT BỊ ADB TRONG DEVICE MANAGER - trạng thái CHI TIẾT")
print(ps("Get-PnpDevice -Class AndroidUsbDeviceClass -EA SilentlyContinue "
         "| Select-Object Status,Present,InstanceId | Format-List | Out-String"))

print("5) MÃ LỖI CỦA THIẾT BỊ (ConfigManagerErrorCode)")
print(ps("Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'ADB|Android' } "
         "| Select-Object Name,ConfigManagerErrorCode,Status,DeviceID "
         "| Format-List | Out-String"))

print("6) PHẦN MỀM CÓ THỂ GIÀNH THIẾT BỊ")
print(ps("Get-Process | Where-Object { $_.Name -match 'Kies|Smart Switch|SAMSUNG|PhoneLink|YourPhone|scrcpy|HiSuite' } "
         "| Select-Object Name,Id | Format-Table -AutoSize | Out-String") or "   (không có)")

print("\n7) adb devices (chi tiết)")
print("   " + sh("adb", "devices", "-l").replace("\n", "\n   "))
