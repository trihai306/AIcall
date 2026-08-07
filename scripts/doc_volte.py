"""Đọc mọi thiết lập liên quan VoLTE trước khi đụng vào. Chỉ đọc, không đổi."""
import subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
S = "21f10e44220c7ece"

def sh(cmd, root=False):
    full = f"su -c '{cmd}'" if root else cmd
    r = subprocess.run(["adb","-s",S,"shell",full], capture_output=True, text=True, timeout=40)
    return ((r.stdout or "") + (r.stderr or "")).strip()

print("CÀI ĐẶT HỆ THỐNG (settings global)")
for k in ("volte_vt_enabled", "preferred_network_mode", "preferred_network_mode1",
          "preferred_network_mode2", "wfc_ims_enabled", "vt_ims_enabled",
          "enhanced_4g_mode_enabled", "data_roaming"):
    print(f"  {k:<28} {sh(f'settings get global {k}')}")

print("\nTHUỘC TÍNH HỆ THỐNG (getprop)")
for k in ("persist.dbg.volte_avail_ovr", "persist.dbg.vt_avail_ovr",
          "persist.dbg.wfc_avail_ovr", "persist.radio.calls.on.ims",
          "ro.telephony.default_network", "ril.subscription.types",
          "gsm.network.type", "gsm.operator.numeric", "gsm.sim.operator.numeric"):
    v = sh(f"getprop {k}")
    print(f"  {k:<32} {v or '(trống)'}")

print("\nCSC / cấu hình nhà mạng Samsung")
for k in ("ro.csc.sales_code", "ril.official_cscver", "persist.omc.sales_code",
          "ro.csc.country_code"):
    print(f"  {k:<32} {sh(f'getprop {k}') or '(trống)'}")

print("\nCÓ QUYỀN ROOT KHÔNG")
print("  " + (sh("id", root=True) or "(không trả lời)"))

print("\nDỊCH VỤ IMS CÓ CHẠY KHÔNG")
out = sh("dumpsys activity services | grep -i -c ims")
print(f"  số dịch vụ có chữ 'ims': {out}")
print("  " + (sh("pm list packages | grep -i -E 'ims|volte'").replace("\n", "\n  ") or "(không có gói nào)"))
