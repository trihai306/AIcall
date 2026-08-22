"""Soi trang thai app cau noi tieng tren dien thoai. Chi DOC, khong goi, khong ghi."""
import re, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S="21f10e44220c7ece"
def adb(*a, t=25):
    p=subprocess.run(["adb","-s",S,*a], capture_output=True, text=True,
                     encoding="utf-8", errors="replace", timeout=t)
    return (p.stdout or "")+(p.stderr or "")
print("=== dịch vụ cầu nối có đang chạy không")
d=adb("shell","dumpsys","activity","services","com.tuktech.voicebridge")
if "ServiceRecord" in d:
    for l in d.splitlines():
        if any(k in l for k in ("ServiceRecord","isForeground","startRequested",
                                "app=","createTime","lastActivity")):
            print("   ", l.strip()[:120])
else:
    print("    KHÔNG có dịch vụ nào đang chạy")
print("\n=== tiến trình app")
print("   ", (adb("shell","pidof","com.tuktech.voicebridge").strip() or "KHÔNG chạy"))
print("\n=== adb forward đang mở")
print("   ", (adb("forward","--list").strip() or "không có"))
print("\n=== logcat: dòng nào nhắc tới cầu nối / AudioRecord")
lg=adb("logcat","-d","-t","3000")
kw=("voicebridge","BridgeService","AudioRecord","AudioTrack","VOICE_CALL","permission")
d=[l for l in lg.splitlines() if any(k.lower() in l.lower() for k in kw)]
print(f"    ({len(d)} dòng khớp)")
for l in d[-25:]: print("   ", l[:150])
print("\n=== trạng thái cuộc gọi hiện tại")
for l in adb("shell","dumpsys","telephony.registry").splitlines():
    if "mCallState" in l or "mServiceState" in l[:40]:
        print("   ", l.strip()[:110])
