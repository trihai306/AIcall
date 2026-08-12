"""Dat lai mixer ve mac dinh sau khi da nghich tuyen usb.

Lay dung bo control cua _tuyen_usb(on=False) trong adb_service: no khoi phuc
NSRC1 va co ERAP - hai thu ma _tuyen_codec KHONG dung toi (vi no gia dinh
chung dang o mac dinh).
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
S, M = "21f10e44220c7ece", "/data/local/tmp/mixctl"

TAT_USB = ([(f"ABOX SPUS OUT{i}", "SIFS0") for i in range(6)] +
           [("ABOX NSRC1", "UAIF0"), ("ABOX ERAP info USB On", "0"),
            ("ABOX UAIF0 SPK", "RESERVED"),
            ("AIF1TX1 Input 1", "ASRC1IN1L"),
            ("AIF1TX2 Input 1", "ASRC1IN1R")])


def chay(dat, nhan):
    lenh = "; ".join(f'{M} set "{t}" "{g}"' for t, g in dat)
    r = subprocess.run(["adb", "-s", S, "shell", f"su -c '{lenh}'"],
                       capture_output=True, text=True, timeout=60)
    ok = r.stdout.count("da dat")
    print(f"{nhan}: {ok}/{len(dat)} control")
    if ok < len(dat):
        print("  ", (r.stdout + r.stderr).strip()[:300])


def doc(ten):
    lenh = "; ".join(f'{M} get "{t}"' for t in ten)
    r = subprocess.run(["adb", "-s", S, "shell", f"su -c '{lenh}'"],
                       capture_output=True, text=True, timeout=40)
    for d in r.stdout.splitlines():
        if d.strip():
            print("   ", d.strip())


print("=== TRUOC ===")
doc(["ABOX NSRC1", "ABOX ERAP info USB On", "ABOX UAIF0 SPK", "AIF1TX1 Input 2"])
print()
chay(TAT_USB, "Dat lai mac dinh (tat tuyen usb)")
print("\n=== SAU ===")
doc(["ABOX NSRC1", "ABOX ERAP info USB On", "ABOX UAIF0 SPK", "AIF1TX1 Input 2"])
