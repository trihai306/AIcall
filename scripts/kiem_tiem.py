"""Bộ tiêm tiếng vào đường lên đang ở trạng thái nào?

AIF1TX1 Input 2 = AIF1RX1 nghĩa là tiếng của máy thay micro đi lên. Để nguyên
mà không phát gì thì đầu bên kia nghe IM LẶNG - đúng triệu chứng "không nghe
thấy gì".
"""
import subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=True, t=60):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=t)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("BỘ TIÊM TIẾNG (mixctl)")
for ctl in ("AIF1TX1 Input 1", "AIF1TX1 Input 2",
            "AIF1TX1 Input 1 Volume", "AIF1TX1 Input 2 Volume"):
    # bọc cả lệnh trong nháy đơn, không thì shell tách tên control thành 2 tham số
    ra = sh(f'/data/local/tmp/mixctl get "{ctl}"')
    print(f"  {ctl:<26} = {ra[:60] if ra else '(không đọc được)'}")

print("\nMICRO CÓ BỊ TẮT TIẾNG KHÔNG")
au = sh("dumpsys audio | grep -i -m4 -E 'mic mute|MicMute|mute'", root=False)
print("  " + (au.replace("\n", "\n  ")[:300] if au else "(không đọc được)"))

print("\nCẦU TIẾNG CÓ ĐANG CHẠY KHÔNG")
print(f"  app: {'có' if 'voicebridge' in sh('ps -A | grep voicebridge', root=False) else 'không chạy'}")
port = sh("netstat -an 2>/dev/null | grep 8123", root=False)
print(f"  cổng 8123: {'đang nghe' if 'LISTEN' in port else 'không nghe'}")
